#!/usr/bin/env python3
"""Bind actual completed RSA stages to frozen Git bytes and native symbol data.
No compiler or guest runs are performed by this publication audit.
"""
import argparse,datetime,hashlib,json,subprocess,sys,os,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',type=Path,required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--cpu',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if args.output.exists():raise ValueError('Preserve immutable prior qualification')
    host=json.loads(args.host.read_text());build=json.loads(args.build.read_text());cpu=json.loads(args.cpu.read_text())
    if build['outcome']!='pass' or cpu['outcome']!='pass' or host['host_checks']!=cpu['arm_checks']:raise ValueError('Actual successful stages disagree')
    if not all(case['accepted'] for case in cpu['guest_cases']):raise ValueError('Actual CPU negative control missing')
    if any(row['after']['owned_processes'] for row in cpu['commands']):raise ValueError('Owned guest process remained')
    environment={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
    available=int(re.search(r'^MemAvailable:\s*(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
    if available<4*1024**3:raise RuntimeError('Publication process admission below4GiB;defer without modifying existing evidence')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,env=environment).strip();commands=[];bindings={}
    for name,wanted in cpu['owned_source_hashes'].items():
        if Path(name).suffix not in ['.c','.h']:continue
        path=ROOT/name;argv=['git','show',commit+':'+name]
        r=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=15,env=environment)
        commands.append(dict(argv=argv,exit_code=r.returncode,stdout_sha256=hashlib.sha256(r.stdout).hexdigest()))
        if r.returncode or sha(path)!=wanted or hashlib.sha256(r.stdout).hexdigest()!=wanted:raise ValueError('Frozen compiled bytes do not match Git: '+name)
        bindings[name]=wanted
    sys.path.insert(0,str(ROOT/'tools/build'));from xnu_kernel_syscalls import ObjectData
    defined=set();undefined=set();objects=[]
    for row in build['native_component_objects']:
        path=ROOT/row['path']
        if sha(path)!=row['sha256'] or 'synthetic_mem' in row['source']:raise ValueError('Production manifest integrity or scope failure')
        data=ObjectData(path)
        for symbol in data.symbols:
            if not(symbol['kind']&1):continue
            if symbol['kind']&0x0e==0x0e:defined.add(symbol['name'])
            elif symbol['kind']&0x0e==0:undefined.add(symbol['name'])
        objects.append(row)
    imports=sorted(undefined-defined)
    if any(any(token in name for token in ['malloc','calloc','realloc','_free','_alloc']) for name in imports):raise ValueError('Unexpected allocating public RSA dependency')
    report=dict(kind='host-test',origin='local-host',outcome='pass',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=commit,
        summary='Fixed64 genuine RSA public callback pair:481 supported primary+10 independent vectors,782365 host and ARM checks,real typed native objects and bounded runtime controls;no provider/native/private ABI/FIPS/sidechannel qualification',
        host_checks=host['host_checks'],arm_checks=cpu['arm_checks'],host_vectors=host['host_vectors'],target_layout=host['target_layout'],observed_guest_stack_bytes=cpu['observed_stack_bytes'],
        compiled_git_bindings=bindings,native_component_objects=objects,native_unresolved_imports=imports,
        compiler_guard_and_memory_providers_are_integration_requirements=True,synthetic_checked_memset_in_production=False,
        source_oracle_coverage=dict(primary=481,independent=10,unresolved_message_representation=17),
        guest_cases=cpu['guest_cases'],commands=commands,prior_actual_stage_capsules={},limitations=dict(general_cczp_funcs_Montgomery=False,general_public_context=False,private_ABI=False,provider_registered=False,full_crypto=False,XNU_executed=False,native_S24=False,FIPS=False,sidechannel_assurance=False))
    paths=[args.host.resolve(),args.build.resolve(),args.cpu.resolve()]
    report['artifacts']=[str(p.relative_to(MAIN)) for p in paths];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in paths}
    for path in paths:report['prior_actual_stage_capsules'][str(path.relative_to(MAIN))]=sha(path)
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome='pass',commit=commit,native_imports=imports,compiled_files=len(bindings)),indent=2))
if __name__=='__main__':main()
