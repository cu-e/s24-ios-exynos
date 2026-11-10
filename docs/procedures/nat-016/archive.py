#!/usr/bin/env python3
"""Host-only bounded archive for framed early logs. No phone commands or resets.

Input: newline-delimited JSON frames, with boot_id, seq, kind and data_b64.
The exact received bytes are saved before parsing. Transport remains unqualified.
"""
import argparse
import base64
import binascii
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import sys
import time

MAX_FRAME = 65536
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z')

def stamp():
    return dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                monotonic_ns=time.monotonic_ns())

def create(path):
    return open(path, 'xb', buffering=0)

def durable(f, data):
    view = memoryview(data)
    while view:
        n = f.write(view)
        if not n:
            raise OSError('archive write made no progress')
        view = view[n:]
    os.fsync(f.fileno())

def row(f, value):
    durable(f, (json.dumps(value, sort_keys=True, separators=(',', ':'))+'\n').encode())

def seal_json(path, value):
    with create(path) as f:
        row(f, value)

def sync_dir(path):
    fd=os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)

def digest_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(1024*1024):h.update(chunk)
    return h.hexdigest()

class Archive:
    def __init__(self, out, channel, provenance):
        if not ID.fullmatch(channel):
            raise ValueError('invalid channel name')
        # Refuse reuse, including symlinks. Every invocation is a new attempt.
        out.mkdir(parents=True, exist_ok=False)
        self.out=out
        self.raw=create(out/'received.bin')
        self.index=create(out/'chunks.jsonl')
        self.events=create(out/'events.jsonl')
        self.offset=0
        self.boots={}
        self.seen_ids=set()
        self.current=None
        self.errors=0
        self.pending=bytearray()
        self.discarding=False
        seal_json(out/'attempt.json',dict(schema='early-log-archive-v1', **stamp(),
                  channel=channel, provenance=provenance, transport_qualified=False,
                  meaning='Host receipt only; frames do not prove hardware execution.'))
        sync_dir(out)
        sync_dir(out.parent)

    def error(self, reason, **extra):
        self.errors+=1
        row(self.events,dict(**stamp(), kind='capture-error',reason=reason,**extra))

    def frame(self, line):
        try:
            f=json.loads(line)
            if not isinstance(f,dict): raise ValueError('frame must be an object')
            bid=f['boot_id']; seq=f['seq']; kind=f['kind']
            if not isinstance(bid,str) or not ID.fullmatch(bid):raise ValueError('invalid boot_id')
            if type(seq) is not int or not 0<=seq<2**64:raise ValueError('invalid seq')
            if kind not in ('boot','log','stage','fault','end','drop'):raise ValueError('invalid kind')
            payload=base64.b64decode(f.get('data_b64',''),validate=True)
            if kind=='boot':
                if seq!=0:raise ValueError('nonzero boot sequence')
                if bid in self.seen_ids:self.error('reused boot_id',boot_id=bid)
                if len(self.boots)>=4096:raise ValueError('boot-count bound reached')
                record=f'{len(self.boots)+1:06d}-{bid}'
                if self.current is not None:
                    row(self.events,dict(**stamp(),kind='boundary',previous=self.current,
                        next=record,reason='explicit-producer-boot-marker; reset cause unverified'))
                    old=self.boots[self.current]
                    old['frames'].close();old['payload'].close()
                folder=self.out/'boots'/record
                folder.mkdir(parents=True,exist_ok=False)
                rec=dict(folder=folder,frames=create(folder/'frames.jsonl'),
                         payload=create(folder/'payload.bin'),next_seq=0,ended=False,boot_id=bid)
                self.boots[record]=rec;self.current=record;self.seen_ids.add(bid)
                sync_dir(folder);sync_dir(folder.parent)
            if self.current is None:raise ValueError('missing current boot marker')
            rec=self.boots[self.current]
            if bid!=rec['boot_id']:raise ValueError('missing current boot marker')
            if rec['ended']:raise ValueError('frame after end')
            if seq<rec['next_seq']:raise ValueError('duplicate or reversed sequence')
            if seq!=rec['next_seq']:
                self.error('sequence-gap',boot_id=bid,expected=rec['next_seq'],received=seq)
            durable(rec['payload'],payload)
            row(rec['frames'],dict(received=stamp(),frame=f))
            rec['next_seq']=seq+1
            rec['ended']=kind=='end'
            if kind=='drop':self.error('producer-reported-drop',boot_id=bid,seq=seq)
        except (ValueError,TypeError,KeyError,binascii.Error) as e:
            self.error('invalid-frame',detail=str(e))

    def receive(self, data):
        # Archive first, including malformed bytes; decoding never replaces raw data.
        durable(self.raw,data)
        row(self.index,dict(**stamp(),offset=self.offset,length=len(data),sha256=hashlib.sha256(data).hexdigest()))
        self.offset+=len(data)
        self.pending.extend(data)
        while True:
            end=self.pending.find(b'\n')
            if end<0:
                if len(self.pending)>MAX_FRAME:
                    if not self.discarding:self.error('oversize-frame')
                    self.discarding=True;self.pending.clear()
                break
            line=bytes(self.pending[:end]);del self.pending[:end+1]
            if self.discarding:self.discarding=False;continue
            if len(line)>MAX_FRAME:self.error('oversize-frame')
            else:self.frame(line)

    def finish(self, stop):
        if self.pending or self.discarding:self.error('truncated-frame')
        if stop!='eof':self.error(stop)
        for bid,rec in self.boots.items():
            if not rec['ended']:self.error('boot-without-end',boot_id=bid)
        row(self.events,dict(**stamp(),kind='collector-stop',reason=stop,bytes_received=self.offset))
        self.raw.close();self.index.close();self.events.close()
        for rec in self.boots.values():rec['frames'].close();rec['payload'].close()
        files={}
        for p in sorted(self.out.rglob('*')):
            if p.is_file():files[str(p.relative_to(self.out))]=digest_file(p)
        result=dict(**stamp(),schema='early-log-manifest-v1',stop=stop,
            bytes_received=self.offset,boots=list(self.boots),errors=self.errors,
            outcome='complete-received-stream' if self.boots and not self.errors else 'incomplete',
            transport_qualified=False,hardware_execution_proven=False,sha256=files)
        seal_json(self.out/'manifest.json',result);sync_dir(self.out)
        return result

def collect(fd,out,channel,provenance,seconds,max_bytes):
    if not 0<seconds<=3600 or not 0<max_bytes<=1024**3:raise ValueError('invalid time/size bound')
    archive=Archive(out,channel,provenance)
    deadline=time.monotonic()+seconds
    try:
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:stop='deadline';break
            if archive.offset>=max_bytes:stop='size-limit';break
            ready,_,_=select.select([fd],[],[],remaining)
            if not ready:stop='deadline';break
            data=os.read(fd,min(8192,max_bytes-archive.offset))
            if not data:stop='eof';break
            archive.receive(data)
    except KeyboardInterrupt:
        stop='interrupted'
    except OSError as e:
        archive.error('io-error',detail=str(e));stop='io-error'
    return archive.finish(stop)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--input',default='-',help='stdin, local regular file or existing FIFO; no device nodes')
    p.add_argument('--channel',required=True)
    p.add_argument('--provenance',choices=['synthetic','unqualified-live'],required=True)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--max-bytes',type=int,default=32*1024*1024)
    a=p.parse_args()
    fd=sys.stdin.fileno();owned=False
    if a.input!='-':
        before=os.lstat(a.input)
        if not (stat.S_ISREG(before.st_mode) or stat.S_ISFIFO(before.st_mode)):
            raise ValueError('only regular files and FIFOs are accepted; no symlinks or device nodes')
        fd=os.open(a.input,os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW);owned=True
        after=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):
            os.close(fd);raise ValueError('only regular files and FIFOs are accepted')
    try:result=collect(fd,a.out,a.channel,a.provenance,a.seconds,a.max_bytes)
    finally:
        if owned:os.close(fd)
    print(json.dumps(result,indent=2))
    return 0 if result['outcome']=='complete-received-stream' else 2

if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError) as e:print(f'archive: {e}',file=sys.stderr);sys.exit(2)
