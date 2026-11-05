#!/usr/bin/env python3
"""Reuse frozen successful RSA stages;test CPU-only checked fill and relink."""
import argparse,datetime,hashlib,json,re,sys
from pathlib import Path
import check
HERE=check.HERE;ROOT=check.ROOT;MAIN=check.MAIN
def sha(path):return check.sha(path)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--prior',type=Path,required=True);args=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('Fresh canonical run required')
    out=ROOT/'artifacts/crypto-rsa'/args.run;out.mkdir(parents=True,exist_ok=False)
    old_path=args.prior.resolve();old=json.loads(old_path.read_text());old_dir=old_path.parent
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],summary='Reused actual successful RSA host/native stages plus new independently tested checked-fill CPU runtime and real payload links;no guest executed',provider_registered=False,native_device=False,QEMU_executed=False,prior_capsule=str(old_path.relative_to(MAIN)),prior_sha256=sha(old_path))
    def command(argv,name,seconds=30):
        memory=check.memory_gate();r=check.shared.run(argv,out,name,seconds,256);r['MemAvailable_before_bytes']=memory;report['commands'].append(r)
        if r['exit_code'] or r['outcome']!='pass':raise RuntimeError(name+' failed;actual log retained')
        return r
    try:
        if old.get('host_vectors')!=491 or old.get('host_checks')!=782365 or old.get('target_layout')!=[1584,8,64,8,24,24,1568,24]:raise ValueError('Required actual completed stages missing')
        if not all(c['detected'] for c in old['sanitizer_controls']):raise ValueError('Missing prior actual sanitizer controls')
        report['host_vectors']=old['host_vectors'];report['host_checks']=old['host_checks'];report['target_layout']=old['target_layout'];report['sanitizer_controls']=old['sanitizer_controls']
        for name,digest in old['owned_source_hashes'].items():
            path=ROOT/name
            if path.suffix in ['.c','.h'] and sha(path)!=digest:raise ValueError('Frozen compiled source changed: '+name)
        for name,digest in old['artifact_hashes'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Frozen build output changed: '+name)
        for path,digest in old['shared_zeroizer'].items():
            if sha(path)!=digest:raise ValueError('Shared zeroizer object changed')
        report['native_component_objects']=old['native_component_objects']
        if any('synthetic_mem' in row['source'] for row in report['native_component_objects']):raise ValueError('Synthetic helper leaked into production manifest')
        host=Path('/home/egor/.local/bin/clang').resolve()
        command([host,'--target=x86_64-unknown-linux-gnu','-O1','-Wall','-Wextra','-Werror','-fno-builtin',HERE/'synthetic_mem.c',HERE/'synthetic_mem_test.c','-o',out/'checked-memory-test'],'checked-memory-build')
        command([out/'checked-memory-test'],'checked-memory-tests')
        if 'RSA CHECKED MEMSET PASS' not in (out/'checked-memory-tests.log').read_text():raise ValueError('Missing actual checked-fill control result')
        template=next(c['argv'] for c in old['commands'] if '-c' in c['argv'] and str(old_dir/'cpu-adapter.o') in c['argv'])
        argv=list(template);argv[argv.index(str(HERE/'rsa.c'))]=str(HERE/'synthetic_mem.c')
        argv[argv.index('-o')+1]=str(out/'cpu-checked-memory.o');argv[argv.index('-MF')+1]=str(out/'cpu-checked-memory.d')
        command(argv,'cpu-checked-memory')
        link=next(c['argv'] for c in old['commands'] if '-static' in c['argv'] and '-e' in c['argv'])
        report['images']={}
        for mode,guest in [('normal','guest'),('spin','spin')]:
            argv=[str(old_dir/('cpu-'+guest+'.o')) if str(arg)==str(old_dir/'cpu-guest.o') else str(arg) for arg in link]
            argv[argv.index('-o')+1]=str(out/(mode+'.macho'));argv.insert(argv.index('-o'),str(out/'cpu-checked-memory.o'))
            command(argv,mode+'-link');report['images'][mode]=check.shared.avf.macho(out/(mode+'.macho'))
        # Actual consumed header identities are checked after frozen-object
        # reuse,without modifying any shared source or rebuilding the kernel.
        report['dependency_hashes']={};report['canonical_selected_headers']={}
        xts=json.loads((ROOT/'docs/procedures/crypto-xts/qualified-evidence.json').read_text())
        for dep in old_dir.glob('*.d'):
            for name in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
                path=Path(name).resolve();digest=sha(path);report['dependency_hashes'][str(path)]=digest
                if '/corecrypto/' in name and '/EXTERNAL_HEADERS/' in name:
                    rel='EXTERNAL_HEADERS/'+name.split('/EXTERNAL_HEADERS/',1)[1]
                    if rel not in report['canonical_selected_headers']:
                        argv=['git','-C',str(MAIN/'references/apple-xnu'),'show','c54f35ca767986246321eb901baf8f5ff7923f6a:'+rel]
                        import subprocess,os
                        r=subprocess.run(argv,capture_output=True,env={**os.environ,**check.GUARDS},timeout=15)
                        report['commands'].append(dict(argv=argv,exit_code=r.returncode,stdout_sha256=hashlib.sha256(r.stdout).hexdigest()))
                        if r.returncode or hashlib.sha256(r.stdout).hexdigest()!=digest:raise ValueError('Canonical selected header differs: '+rel)
                        report['canonical_selected_headers'][rel]=digest
                if path.is_relative_to(ROOT/'src/platform/crypto/xts'):
                    rel=str(path.relative_to(ROOT))
                    if xts['owned_source_hashes'].get(rel)!=digest:raise ValueError('Accepted full shared dependency differs: '+rel)
        report['outcome']='pass'
    except Exception as error:report['error']=repr(error)
    report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    report['memory_gate_observations']=check.GATE_OBSERVATIONS
    report['artifact_hashes']={str(p.relative_to(ROOT)):sha(p) for p in out.rglob('*') if p.is_file()}
    report['artifacts']=[str((ROOT/name).relative_to(MAIN)) for name in report['artifact_hashes']]
    report['sha256']={str((ROOT/name).relative_to(MAIN)):value for name,value in report['artifact_hashes'].items()}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','error','host_vectors','host_checks','images']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
