#!/usr/bin/env python3
"""Offline real-parser checks and independent stock byte identity."""
from pathlib import Path
import tarfile,hashlib,subprocess,json,io
root=Path(__file__).resolve().parents[3]; out=root/'artifacts/nat-008'
package=root/'artifacts/nat-006/build-002/restore/recovery-stock-odin.tar'
blob=package.read_bytes()
assert hashlib.sha256(blob).hexdigest()=='2787aa3e07d1f09d5f2c808166e0640719f111a618105ceed1ef67ea721fe84e'
with tarfile.open(package) as tar:
    members=tar.getmembers(); assert len(members)==1
    m=members[0]; assert m.name=='recovery.img' and m.isfile() and m.size==100663296
    assert hashlib.sha256(tar.extractfile(m).read()).hexdigest()=='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'
rows=[]
def check(p,expected):
    argv=[str(out/'offline'),str(p)]; r=subprocess.run(argv,capture_output=True,text=True)
    rows.append(dict(argv=argv,exit_code=r.returncode,expected=expected,stdout=r.stdout,stderr=r.stderr)); assert r.returncode==expected
check(package,0)
p=out/'bad-checksum.tar'; data=bytearray(blob[:1024]); data[0]^=1; p.write_bytes(data); check(p,4)
p=out/'truncated.tar'; p.write_bytes(blob[:1024]); check(p,4)
p=out/'wrong-partition.tar'
with tarfile.open(p,'w',format=tarfile.USTAR_FORMAT) as tar:
    m=tarfile.TarInfo('boot.img'); m.size=4; tar.addfile(m,io.BytesIO(b'test'))
check(p,5)
(out/'parser-checks.json').write_text(json.dumps(rows,indent=2)+'\n')
print('PASS: stock bytes and real odin4 parser; 3 negative controls rejected')
