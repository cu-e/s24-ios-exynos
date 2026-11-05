#!/usr/bin/env python3
"""Independent byte audit and small actual pthread/header/MIG reproductions."""
from collections import Counter
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys
from object_reader import Object, members

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]; MAIN = WT.parents[1]
BASE = MAIN/'artifacts/xnu-kernel-pthread-profile'
OUT = WT/'artifacts/rev-krn-022'/sys.argv[1]
OUT.mkdir(parents=True,exist_ok=False)
TIP = '16a7497ef0243a3c4fbdfa7ec5189a864a6a4f88'
ENV = dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
commands,checks = [],[]

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(MAIN))
def passed(name,**kw):checks.append(dict(name=name,pass_check=True,**kw))
def run(label,argv,cwd=WT,codes=(0,),timeout=45):
    argv=[str(a) for a in argv]
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    p=subprocess.run(argv,cwd=cwd,env=ENV,capture_output=True,timeout=timeout)
    a,b=OUT/(label+'.stdout'),OUT/(label+'.stderr');a.write_bytes(p.stdout);b.write_bytes(p.stderr)
    commands.append(dict(argv=argv,cwd=str(cwd),exit_code=p.returncode,started_at=start,
        ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stdout=rel(a),stderr=rel(b),
        timed_out=False,environment={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE']}))
    assert p.returncode in codes,(label,p.returncode,p.stderr.decode(errors='replace')[-2000:])
    return p.stdout
def loaded(runname):return json.loads((BASE/runname/'report.json').read_text())
def command(report,suffix):return next(c for c in report['commands'] if c['stdout'].endswith('/'+suffix+'.stdout.txt'))
def fresh_compile(label,original):
    argv=original['argv'].copy();output=OUT/(label+'.o')
    argv[argv.index('-o')+1]=str(output);argv[argv.index('-MF')+1]=str(output.with_suffix('.d'))
    run(label,argv,cwd=Path(original['cwd']))
    return Object(output.read_bytes())

report=dict(kind='source-review',origin='local-host',outcome='fail',commit=TIP,
    recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=commands,checks=checks,
    device_executed=False,summary='Independent genuine pthread component byte/source audit and bounded actual reproductions')
try:
    sources=['tools/build/xnu_kernel_pthread_profile.py','fixtures/public/xnu-kernel-pthread-profile/qualified-component.json',
             'docs/procedures/xnu-kernel-pthread-profile.md']
    for i,name in enumerate(sources):
        data=run('exact-source-'+str(i),['git','-C',MAIN,'cat-file','blob',TIP+':'+name])
        assert data==(MAIN/name).read_bytes()
    report['source_sha256']={n:sha(MAIN/n) for n in sources}
    report['review_base_commit']=run('review-base',['git','rev-parse','HEAD']).decode().strip()
    run('python-version',[sys.executable,'--version'])
    for repo,revision in [('xnu-kernel-pthread','a6c70ca0e544347a0377babf748f831577ec24f9'),('apple-xnu','c54f35ca767986246321eb901baf8f5ff7923f6a')]:
        assert run(repo+'-pin',['git','-C',MAIN/'references'/repo,'rev-parse','HEAD']).decode().strip()==revision
        run(repo+'-clean',['git','-C',MAIN/'references'/repo,'diff','--exit-code','HEAD'])
    passed('exact-three-reviewed-source-blobs-and-two-pinned-clean-references')
    capsules={}
    for name in ['headers-session4','compile-session2','controls-session1','aliases-session1','native-mig-session2','acceptance-session1']:
        path=BASE/name/'evidence.json';doc=json.loads(path.read_text())
        assert doc['outcome']=='pass'
        for p,h in doc['sha256'].items():assert sha(MAIN/p)==h,p
        r=loaded(name);assert all(c['pass_check'] for c in r['checks'])
        capsules[name]=dict(evidence=rel(path),sha256=sha(path),artifacts=len(doc['sha256']),checks=len(r['checks']))
    report['capsules']=capsules
    assert capsules['acceptance-session1']['checks']==21
    passed('all-six-capsules-actual-artifact-hashes-and-passing-check-records',capsules=capsules)
    header,component,controls,alias,mig,accept=[loaded(n) for n in capsules]
    manifest=json.loads((BASE/'headers-session4/installed-header-manifest.json').read_text())
    counts=Counter(r['status'] for r in manifest)
    assert counts=={'installed':1794,'native_filtered_empty':36,'unavailable_generated_input':76}
    for row in manifest:
        assert sha(MAIN/row['declaration'])==row['declaration_sha256']
        if row.get('source_sha256'):assert sha(MAIN/row['source'])==row['source_sha256']
        if row['status']=='installed':
            assert sha(MAIN/row['output'])==row['output_sha256']
            assert (MAIN/row['output']).stat().st_mode&0o777==0o444
        else:assert not (MAIN/row['output']).exists()
    thread=next(r for r in manifest if r['private'] and r['output'].endswith('/kern/thread.h'))
    assert all(f in thread['unifdef_flags'] for f in ['-UXNU_KERNEL_PRIVATE','-UMACH_KERNEL_PRIVATE','-UBSD_KERNEL_PRIVATE'])
    assert re.search(r'\bstruct\s+thread\s*\{',(MAIN/thread['source']).read_text())
    out=OUT/'thread-installed.h';unifdef=MAIN/header['header_install_tools']['unifdef']
    run('fresh-native-thread-unifdef',[unifdef,*thread['unifdef_flags'],'-o',out,MAIN/thread['source']],codes=(0,1))
    assert out.read_bytes()==(MAIN/thread['output']).read_bytes()
    assert not re.search(r'\bstruct\s+thread\s*\{',out.read_text())
    passed('all-installed-source-hashes-modes-unavailable-inputs-and-fresh-real-thread-unifdef',counts=dict(counts))
    closure=component['pthread_provider_closure'];archive=MAIN/closure['archive']
    assert sha(archive)==closure['sha256']
    actual=members(archive.read_bytes());assert len(actual)==3
    definitions,imports=set(),set()
    for (name,data),row in zip(actual,component['pthread_compile_results']):
        assert name==Path(row['output']).name and data==(MAIN/row['output']).read_bytes()
        view=Object(data);definitions.update(view.exported());imports.update(view.imported())
    imports-=definitions
    assert sorted(definitions)==closure['defined'] and sorted(imports)==closure['external_imports']
    sgap=MAIN/'artifacts/xnu-kernel-symbol-gaps/production-session1'
    compiled=json.loads((sgap/'compiled-objects.json').read_text());assert len(compiled)==982
    byid={r['id']:r for r in compiled};kernel_definitions=set()
    for row in compiled:
        assert sha(MAIN/row['source'])==row['source_sha256'] and sha(MAIN/row['output'])==row['output_sha256']
        kernel_definitions.update(Object((MAIN/row['output']).read_bytes()).exported())
    aliases={k:v['target'] for k,v in component['native_VM_aliases'].items()}
    unresolved={s for s in imports if s not in kernel_definitions and aliases.get(s) not in kernel_definitions}
    assert not unresolved and not definitions&kernel_definitions
    assert len(definitions)==39 and len(imports)==61
    report['archive']=dict(sha256=sha(archive),definitions=sorted(definitions),imports=sorted(imports),
                          kernel_objects=len(compiled),kernel_definitions=len(kernel_definitions),unresolved=[],overlap=[])
    for file in ['pthread-dependency-files.json']:
        for name,h in json.loads((BASE/'compile-session2'/file).read_text()).items():assert sha(MAIN/name)==h
    passed('independent-archive-reader-all-members-imports-and-actual982-provider-closure',definitions=39,imports=61)
    layout=controls['callback_layout'];observed={}
    for label,row in layout['probes'].items():
        obj=Object((MAIN/row['object']).read_bytes())
        observed[label]=obj.values('_s24_pthread_layout',284)
        assert observed[label]==row['layout']
        assert obj.values('_s24_kalloc_layout',4)==[64,32,40,44]
    assert observed['kext']==observed['kernel']==layout['clang19_values']
    assert {k:len(v) for k,v in layout['fields'].items()}=={'pthread_functions_s':45,'pthread_callbacks_s':95}
    # Recompare full actual preprocessed declarations, not hand-invented struct tables.
    declarations={}
    for label in ['kext','kernel']:
        text=(BASE/'controls-session1'/('actual-'+label+'-callback-preprocessing.stdout.txt')).read_text()
        declarations[label]=[]
        for record in ['pthread_functions_s','pthread_callbacks_s']:
            match=re.search(r'typedef\s+const\s+struct\s+'+record+r'\s*\{(.*?)\}\s*\*\s*\w+\s*;',text,re.S)
            assert match
            body=re.sub(r'^#.*$','',match.group(1),flags=re.M)
            declarations[label].append(re.sub(r'\s+','',body))
    assert declarations['kext']==declarations['kernel']
    fresh=fresh_compile('fresh-kext-callback',command(controls,'actual-kext-callback-probe'))
    assert fresh.values('_s24_pthread_layout',284)==observed['kernel']
    passed('independent140-declarations284-values-and-fresh-full-kext-TU-probe',table_sizes=[observed['kext'][0],observed['kext'][92]])
    metadata=controls['allocator_metadata'];real_obj=Object((BASE/'compile-session2/kern_synch.o').read_bytes())
    actual_records=[]
    for name in ['_kwq_zone','_kwe_zone']:
        actual_records.append(dict(name=name,signature=real_obj.string_pointer(name,32),
                                  flags=real_obj.values(name,1,40,'I')[0],size=real_obj.values(name,1,44,'I')[0]))
    assert actual_records==metadata['records']
    fake_obj=Object((BASE/'controls-session1/fake-metadata-negative.o').read_bytes())
    assert all(fake_obj.string_pointer(n,32)=='12' for n in ['_kwq_zone','_kwe_zone'])
    original=command(controls,'actual-wrong-callback-type-rejection');argv=original['argv'].copy()
    argv[argv.index('-o')+1]=str(OUT/'wrong-callback.o');argv[argv.index('-MF')+1]=str(OUT/'wrong-callback.d')
    run('fresh-wrong-real-function-pointer',argv,cwd=Path(original['cwd']),codes=(1,))
    assert not (OUT/'wrong-callback.o').exists()
    assert b'incompatible' in (OUT/'fresh-wrong-real-function-pointer.stderr').read_bytes()
    report['allocator_records']=actual_records
    compiler=Path(command(controls,'actual-kext-callback-probe')['argv'][0])
    assert sha(compiler)==component['compiler_sha256']=='7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
    report['tool_sha256']={str(compiler):sha(compiler),str(unifdef):sha(unifdef)}
    passed('real-allocator-records-genuine-signatures-fake-control-and-fresh-function-type-rejection')
    # A small relocatable link uses the genuine two provider objects and exact native aliases.
    original=command(alias,'actual-genuine-VM-alias-relocatable-link')
    argv=original['argv'].copy();argv[argv.index('-o')+1]=str(OUT/'real-alias.o')
    run('fresh-real-VM-alias-link',argv)
    view=Object((OUT/'real-alias.o').read_bytes())
    for name,target in aliases.items():
        a,b=view.named[name],view.named[target];assert (a['section'],a['value'])==(b['section'],b['value'])
    wrong=Object((MAIN/alias['negative_VM_alias']['object']).read_bytes())
    assert (wrong.named['_vm_fault']['section'],wrong.named['_vm_fault']['value'])!=(wrong.named['_vm_fault_external']['section'],wrong.named['_vm_fault_external']['value'])
    passed('fresh-actual-VM-provider-alias-link-and-independent-wrong-provider-control')
    for row in mig['fresh_native_SDK_MIG_headers']:
        assert sha(MAIN/row['defs_source'])==row['defs_sha256']
        assert sha(MAIN/row['fresh_raw_header'])==row['fresh_raw_sha256']
        assert sha(MAIN/row['native_installed_header'])==sha(MAIN/row['qualified_header'])==row['qualified_sha256']
        assert sha(MAIN/row['preprocessor_provenance'])==row['preprocessor_provenance_sha256']
    original=command(mig,'fresh-native-SDK-MIG-mach_vm.h');argv=original['argv'].copy()
    cwd=OUT/'native-mig';cwd.mkdir();(OUT/'tmp').mkdir();(OUT/'trace').mkdir()
    wrapper=OUT/'preprocess.py';shutil.copyfile(BASE/'native-mig-session2/preprocess.py',wrapper);wrapper.chmod(0o755)
    for i,arg in enumerate(argv):
        if arg.startswith('MIGCC='):argv[i]='MIGCC='+str(wrapper)
        elif arg.startswith('TMPDIR='):argv[i]='TMPDIR='+str(OUT/'tmp')
        elif arg.startswith('S24_MIG_TRACE='):argv[i]='S24_MIG_TRACE='+str(OUT/'trace')
    run('fresh-native-sdk-mach-vm',argv,cwd=cwd)
    row=next(r for r in mig['fresh_native_SDK_MIG_headers'] if r['name']=='mach_vm.h')
    installed=next(r for r in manifest if r['output']==row['qualified_header'])
    run('fresh-mach-vm-unifdef',[unifdef,*installed['unifdef_flags'],'-o',OUT/'mach_vm-installed.h',cwd/'mach_vm.h'],codes=(0,1))
    assert sha(OUT/'mach_vm-installed.h')==row['qualified_sha256']
    passed('all-four-native-MIG-identities-and-one-fresh-real-native-SDK-context-regeneration')
    profile=component['pthread_compile_profile'];flags=profile['flags']
    assert '-Dpthread_kern=pthread_kext_kern' in flags and '-Dcurrent_uthread=pthread_kext_current_uthread' in flags
    assert '-DXNU_NO_TYPE_BUILTINS=0' in flags and not any(a.startswith('-flto') for a in flags)
    assert profile['native_normal_LTO'] is True and profile['measured_kernel_integration_LTO'] is False
    assert all(not accept['acceptance'][k] for k in ['complete_SDK_qualified','stock_Xcode_release_qualified',
              'private_Apple_ABI_qualified','full_crypto_qualified','full_link_qualified','runtime_qualified','native_device_qualified'])
    passed('LTO-remaps-and-explicit-full-system-private-ABI-limits')
    report['outcome']='pass'
except Exception as error:report['error']=repr(error)
finally:
    report['review_input_sha256']={str(p):sha(p) for p in [HERE/'object_reader.py',Path(__file__)]}
    report['max_child_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['limitations']=['No heavy rebuild or full acceptance-chain execution; sequential small compiler/link/header commands only.',
       'No private Apple ABI/complete SDK/full link/crypto/runtime/native qualification. Existing main artifacts and sources are read-only.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    files=sorted(p for p in OUT.rglob('*') if p.is_file())
    evidence={k:report[k] for k in ['kind','origin','outcome','commit','recorded_at','commands','summary','device_executed']}
    evidence.update(artifacts=[rel(p) for p in files],sha256={rel(p):sha(p) for p in files})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),checks=checks,
         commands=len(commands),peak_rss_kib=report['max_child_rss_kib'],evidence=rel(OUT/'evidence.json')),indent=2))
sys.exit(0 if report['outcome']=='pass' else 1)
