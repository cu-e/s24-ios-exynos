#!/usr/bin/env python3
"""Read-only Odin session/PIT diagnostic with exact-length responses, no ZLP.
No firmware-data or partition-write command exists in this diagnostic.
"""
import argparse,datetime,hashlib,json,struct,time
from pathlib import Path
import usb.core,usb.util
p=argparse.ArgumentParser();p.add_argument('--address',type=int,required=True);p.add_argument('--bus',type=int,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
a.out.mkdir(exist_ok=False,parents=True);trace=[]
d=usb.core.find(idVendor=0x04e8,idProduct=0x685d,bus=a.bus,address=a.address)
assert d is not None
usb.util.claim_interface(d,1)
def write(data):
    n=d.write(1,data,timeout=5000);assert n==len(data)
def read(n,timeout=10000):return bytes(d.read(0x81,n,timeout=timeout))
def command(cmd,sub,arg=0,n=8):
    assert (cmd==0x64 and sub in [0,5]) or (cmd==0x65 and sub in [1,2,3]) or (cmd==0x67 and sub==0)
    b=struct.pack('<III',cmd,sub,arg).ljust(1024,b'\0')
    row=dict(cmd=hex(cmd),subcmd=sub,arg=arg,time=datetime.datetime.now(datetime.timezone.utc).isoformat());trace.append(row)
    write(b);r=read(n,120000 if cmd==0x67 else 10000);row['response']=r.hex();row['length']=len(r)
    (a.out/'trace.json').write_text(json.dumps(trace,indent=2)+'\n')
    if n==8:
        assert len(r)==8
        kind,result=struct.unpack('<II',r);assert kind==cmd,(hex(kind),hex(result))
    return r
try:
    write(b'ODIN');r=read(4);assert r==b'LOKE',r
    time.sleep(.2)
    r=command(0x64,0,4);command(0x64,5,1048576)
    r=command(0x65,1);size=struct.unpack('<II',r)[1];assert 28<=size<=65536,size
    pit=bytearray()
    for i in range((size+499)//500):
        r=command(0x65,2,i,n=500);assert len(r)==min(500,size-len(pit)),(i,len(r),size)
        pit.extend(r)
    assert len(pit)==size
    (a.out/'device.pit').write_bytes(pit)
    command(0x65,3)
    command(0x67,0)
    print('Read-only session/PIT/end PASS',hashlib.sha256(pit).hexdigest())
finally:
    (a.out/'trace.json').write_text(json.dumps(trace,indent=2)+'\n')
    usb.util.release_interface(d,1);usb.util.dispose_resources(d)
