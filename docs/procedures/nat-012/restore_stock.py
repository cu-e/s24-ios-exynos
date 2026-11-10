#!/usr/bin/env python3
"""Restricted stock-RECOVERY rescue for this measured e1s only.

Protocol facts cross-checked against pinned Heimdall v2.2.2 and local S-Boot.
No arbitrary image, target, PIT write, erase, EFS option or retry is exposed.
"""
import argparse,datetime,hashlib,json,struct,time
from pathlib import Path
import usb.core,usb.util
ROOT=Path(__file__).resolve().parents[3]
STOCK='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
PIT='a169ae2c9dc0b11066a3738ccc6913fff94c2ed2c458c6aec1c94108c58b891a'
SIZE=100663296
PART=1048576

def validate_pit(b):
    if hashlib.sha256(b).hexdigest()!=PIT: raise ValueError('PIT differs from measured rescue table')
    magic,count=struct.unpack_from('<II',b)
    if magic!=0x12349876 or not 0<count<=512 or len(b)<28+132*count:raise ValueError('invalid PIT extent')
    rows=[]
    for i in range(count):
        off=28+132*i; fields=struct.unpack_from('<9I',b,off)
        name=b[off+36:off+68].split(b'\0')[0]
        rows.append((fields,name))
    matches=[v for v,n in rows if n==b'RECOVERY']
    if len(matches)!=1:raise ValueError('ambiguous RECOVERY')
    v=matches[0]
    if v[:3]!=(0,8,18) or v[5:7]!=(75152,24576) or v[6]*4096!=SIZE:raise ValueError('wrong RECOVERY boundary')
    if sum(x[2]==18 for x,n in rows)!=1:raise ValueError('ambiguous on-wire identifier')
    return v

def packet(cmd,sub,words=()):
    allowed={(0x64,0),(0x64,5),(0x64,2),(0x65,1),(0x65,2),(0x65,3),(0x66,0),(0x66,2),(0x66,3),(0x67,0),(0x67,1)}
    if (cmd,sub) not in allowed:raise ValueError('forbidden command')
    if (cmd,sub)==(0x66,3):
        if len(words)!=8 or words[0]!=0 or words[2:5]!=(0,8,18) or words[6:]!=(0,0):raise ValueError('forbidden target/flags')
        if not 0<words[1]<=30*PART or words[5] not in (0,1):raise ValueError('invalid sequence boundary')
    return struct.pack('<'+'I'*(2+len(words)),cmd,sub,*words).ljust(1024,b'\0')

class Link:
    def __init__(self,d,out):self.d=d;self.out=out;self.trace=[]
    def save(self): (self.out/'trace.json').write_text(json.dumps(self.trace,indent=2)+'\n')
    def write(self,b):
        n=self.d.write(1,b,timeout=120000)
        if n!=len(b):raise RuntimeError(f'short write {n}/{len(b)}; no automatic retry')
    def read(self,n,timeout=120000):
        b=bytes(self.d.read(0x81,n,timeout=timeout))
        if len(b)!=n:raise RuntimeError(f'short read {len(b)}/{n}')
        return b
    def command(self,cmd,sub,words=(),expected=0,n=8):
        row=dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),cmd=hex(cmd),subcmd=sub,words=words);self.trace.append(row);self.save()
        self.write(packet(cmd,sub,words));r=self.read(n)
        if n==8:
            kind,result=struct.unpack('<II',r);row.update(response_kind=hex(kind),result=result);self.save()
            if kind!=cmd or (expected is not None and result!=expected):raise RuntimeError(f'command rejected: {row}')
        else:row.update(length=len(r),sha256=hashlib.sha256(r).hexdigest());self.save()
        return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--bus',type=int,required=True);p.add_argument('--address',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(exist_ok=False,parents=True)
    image=(ROOT/'devices/recovery/backups/2026-11-10/recovery.img').read_bytes()
    if len(image)!=SIZE or hashlib.sha256(image).hexdigest()!=STOCK:raise ValueError('wrong stock bytes')
    # The preceding probe ended its session without a reboot. Resume only.
    d=usb.core.find(idVendor=0x04e8,idProduct=0x685d,bus=a.bus,address=a.address)
    if d is None:raise RuntimeError('exact USB device disappeared')
    usb.util.claim_interface(d,1);link=Link(d,a.out)
    try:
        link.command(0x64,0,(4,),expected=0x38000)
        link.command(0x64,5,(PART,))
        r=link.command(0x65,1,expected=None);size=struct.unpack('<II',r)[1]
        if size!=8192:raise ValueError('unexpected PIT size')
        pit=bytearray()
        for i in range((size+499)//500):pit.extend(link.command(0x65,2,(i,),n=min(500,size-len(pit))))
        validate_pit(pit);(a.out/'device.pit').write_bytes(pit);link.command(0x65,3)
        link.command(0x64,2,(SIZE,0))
        link.command(0x66,0)
        for offset in range(0,SIZE,30*PART):
            chunk=image[offset:offset+30*PART];link.command(0x66,2,(len(chunk),))
            for idx in range(len(chunk)//PART):
                link.write(chunk[idx*PART:(idx+1)*PART]);r=link.read(8)
                kind,ack=struct.unpack('<II',r)
                if (kind,ack)!=(0,idx):raise RuntimeError(f'data ack mismatch {(kind,ack)} index {idx}')
            last=int(offset+len(chunk)==SIZE)
            link.command(0x66,3,(0,len(chunk),0,8,18,last,0,0))
            print('Acknowledged stock bytes:',offset+len(chunk),'/',SIZE,flush=True)
        link.command(0x67,0)
        print('Session end confirmed. Sending authorized normal reboot.',flush=True)
        link.command(0x67,1)
        print('Reboot confirmed; Android/root readback remains required.',flush=True)
    finally:
        link.save();usb.util.release_interface(d,1);usb.util.dispose_resources(d)
if __name__=='__main__':main()
