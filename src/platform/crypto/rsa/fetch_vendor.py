#!/usr/bin/env python3
"""Copy exact MIT BearSSL blobs from an existing read-only pinned Git cache."""
import argparse,datetime,hashlib,json,os,subprocess
from pathlib import Path
REV='7bea48e5e850ab4cafbe68d3765cdaba13a86d6f'
HERE=Path(__file__).resolve().parent
SOURCES=['src/rsa/rsa_i31_pub.c','src/rsa/rsa_i31_pkcs1_vrfy.c','src/rsa/rsa_pkcs1_sig_unpad.c',
 'src/int/i31_decode.c','src/int/i31_decmod.c','src/int/i31_ninv31.c','src/int/i31_modpow2.c',
 'src/int/i31_encode.c','src/int/i31_bitlen.c','src/int/i31_montmul.c','src/int/i31_tmont.c',
 'src/int/i31_fmont.c','src/int/i31_muladd.c','src/int/i31_add.c','src/int/i31_sub.c',
 'src/int/i32_div32.c','src/codec/ccopy.c']
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,required=True);args=p.parse_args()
    out=HERE/'vendor'
    if out.exists():raise ValueError('Preserve existing vendor bytes;fresh destination required')
    out.mkdir();env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
    tree=subprocess.run(['git','-C',str(args.repo),'ls-tree','-r',REV,'--','inc','src','LICENSE.txt'],env=env,capture_output=True,check=True,text=True)
    blobs={line.split('\t')[1]:line.split('\t')[0].split()[2] for line in tree.stdout.splitlines()}
    names=['LICENSE.txt','src/config.h','src/inner.h',*sorted(name for name in blobs if name.startswith('inc/')),*SOURCES]
    records={}
    for name in names:
        argv=['git','-C',str(args.repo),'show',REV+':'+name]
        r=subprocess.run(argv,env=env,capture_output=True,timeout=15,check=True);data=r.stdout
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if blob!=blobs[name]:raise ValueError('Pinned blob identity mismatch: '+name)
        target=out/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        records[name]=dict(sha256=hashlib.sha256(data).hexdigest(),git_blob=blob,bytes=len(data),argv=argv,exit_code=r.returncode)
    (out/'provenance.json').write_text(json.dumps(dict(repository='https://www.bearssl.org/git/BearSSL',revision=REV,license='MIT;original per-file notices and LICENSE.txt retained',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=records,compiled_sources=SOURCES,git_environment={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS']}),indent=2)+'\n')
if __name__=='__main__':main()
