#!/usr/bin/env python3
import datetime,hashlib,json,sys,tarfile,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos');REV='068ff080b369adfac81509f9b57b2afabaf82dc5'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'artifacts/crypto-gcm/source-session2';out.mkdir(parents=True,exist_ok=False);vendor=ROOT/'src/platform/crypto/gcm/vendor'
 report={'kind':'host-test','origin':'upstream','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[{'argv':[sys.executable,*sys.argv],'exit_code':1}],'attempts':[],'summary':'Complete exact source closure and primary NIST data acquisition only;no algorithm qualification'}
 try:
  archive=ROOT/'artifacts/crypto-gcm/source-session1/mbedtls.tar.gz'
  if sha(archive)!='ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937':raise ValueError('Pinned source archive changed')
  with tarfile.open(archive) as tar:
   name='library/constant_time_impl.h';entry=tar.getmember('mbedtls-'+REV+'/'+name)
   (vendor/name).write_bytes(tar.extractfile(entry).read())
  provenance=json.loads((vendor/'provenance.json').read_text());provenance['files'][name]=sha(vendor/name);(vendor/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n');report['backend']=provenance
  urls=['https://csrc.nist.gov/csrc/media/projects/cryptographic-algorithm-validation-program/documents/mac/gcmtestvectors.zip','https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Algorithm-Validation-Program/documents/mac/gcmtestvectors.zip']
  for i,url in enumerate(urls):
   try:
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/zip'})
    with urllib.request.urlopen(request,timeout=45) as response:data=response.read();status=response.status;final=response.url
    path=out/('nist-'+str(i)+'.zip');path.write_bytes(data)
    with zipfile.ZipFile(path) as z:
     if z.testzip():raise ValueError('NIST ZIP CRC mismatch')
     files={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.endswith('.rsp')}
    if len(files)!=6:raise ValueError('Expected six genuine GCM response files')
    report['attempts'].append({'url':url,'status':status,'final_url':final,'archive':str(path.relative_to(MAIN)),'sha256':sha(path),'files':files});report['vectors']=report['attempts'][-1];break
   except Exception as error:report['attempts'].append({'url':url,'error':repr(error)})
  if 'vectors' not in report:raise ValueError('All ordinary official NIST acquisition attempts failed')
  report['outcome']='pass';report['commands'][0]['exit_code']=0
 except Exception as error:report['error']=repr(error)
 report['artifacts']=[str(p.relative_to(MAIN)) for p in out.iterdir() if p.is_file()];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in out.iterdir() if p.is_file()};(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
