#!/usr/bin/env python3
"""Passively save USB enumeration transitions, without opening a USB device.

Not a native console. A new exclusive file and fsync is used for every event;
prior runs and events are never overwritten. No serial number is collected.
"""
from pathlib import Path
import argparse, datetime, json, os, time

def snapshot():
    rows=[]
    for p in sorted(Path('/sys/bus/usb/devices').glob('*')):
        try:
            vendor=(p/'idVendor').read_text().strip()
            if vendor!='04e8':continue
            row=dict(port=p.name,vendor=vendor)
            for key in ['idProduct','busnum','devnum','product','manufacturer']:
                file=p/key
                if file.exists():row[key]=file.read_text().strip()
            rows.append(row)
        except (OSError,ValueError):continue # enumeration can change during reads
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('--seconds',type=int,default=240);a=p.parse_args()
    if not 1<=a.seconds<=360: p.error('bounded duration must be 1..360 seconds')
    a.out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic(); previous=None; count=0
    while time.monotonic()-start<a.seconds:
        current=snapshot()
        if current!=previous:
            event=dict(kind='host-usb-enumeration',native_console=False,
                at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                elapsed_seconds=round(time.monotonic()-start,6),devices=current)
            path=a.out/f'{count:06d}.json'
            with path.open('x') as f:
                json.dump(event,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
            fd=os.open(a.out,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
            print(json.dumps(event),flush=True)
            count+=1;previous=current
        time.sleep(0.5)
    with (a.out/'complete.json').open('x') as f:
        json.dump(dict(events=count,duration_seconds=a.seconds,native_console=False),f)
        f.write('\n');f.flush();os.fsync(f.fileno())

if __name__=='__main__':main()
