#!/usr/bin/env python3
"""Acquire named complete pinned public source files and primary GCM vector data."""
import datetime,hashlib,json,sys,tarfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
HERE=ROOT/'src/platform/crypto/gcm'
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
REV='068ff080b369adfac81509f9b57b2afabaf82dc5'
EXPECTED='ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'artifacts/crypto-gcm/source-session1';out.mkdir(parents=True,exist_ok=False)
 report={'kind':'host-test','origin':'upstream','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[{'argv':[sys.executable,*sys.argv],'exit_code':None}],'artifacts':[],'sha256':{}}
 try:
  tar=out/'mbedtls.tar.gz';url='https://codeload.github.com/Mbed-TLS/mbedtls/tar.gz/'+REV
  with urllib.request.urlopen(url,timeout=45) as response:tar.write_bytes(response.read())
  if sha(tar)!=EXPECTED:raise ValueError('Pinned complete archive differs')
  vendor=HERE/'vendor';vendor.mkdir(parents=True,exist_ok=False)
  names=['library/gcm.c','library/block_cipher.c','library/block_cipher_internal.h','library/constant_time.c','library/constant_time_internal.h','include/mbedtls/gcm.h','include/mbedtls/block_cipher.h','include/mbedtls/cipher.h','include/mbedtls/constant_time.h','LICENSE']
  files={}
  with tarfile.open(tar) as archive:
   for name in names:
    entry=archive.getmember('mbedtls-'+REV+'/'+name)
    if not entry.isfile():raise ValueError('Named genuine regular source required')
    p=vendor/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.extractfile(entry).read());files[name]=sha(p)
  report['backend']={'url':url,'revision':REV,'archive_sha256':sha(tar),'files':files,'license_choice':'Apache-2.0'}
  (vendor/'provenance.json').write_text(json.dumps(report['backend'],indent=2)+'\n')
  nist=out/'gcmtestvectors.zip';url='https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/mac/gcmtestvectors.zip'
  with urllib.request.urlopen(url,timeout=45) as response:nist.write_bytes(response.read())
  with zipfile.ZipFile(nist) as z:
   bad=z.testzip()
   if bad:raise ValueError('Incomplete NIST ZIP: '+bad)
   report['vectors']={'url':url,'archive_sha256':sha(nist),'files':{name:hashlib.sha256(z.read(name)).hexdigest() for name in z.namelist() if name.endswith('.rsp')}}
  report['outcome']='pass';report['commands'][0]['exit_code']=0
 except Exception as error:
  report['error']=repr(error);report['commands'][0]['exit_code']=1
 finally:
  report['artifacts']=[str(p.relative_to(MAIN)) for p in out.rglob('*') if p.is_file()]
  report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()}
  report['summary']='Named pinned genuine Mbed source and primary NIST GCM vectors;no algorithm or device qualification'
  (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:report.get(k) for k in ['outcome','error','backend','vectors']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
