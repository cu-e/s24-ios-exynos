#!/usr/bin/env python3
"""Independent streaming audit; no link/build or shared mutation."""
from collections import Counter
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import shlex
import struct
import subprocess
import sys
import traceback
from object_reader import Object

HERE=Path(__file__).resolve().parent;WT=HERE.parents[2];MAIN=WT.parents[1]
IMPL=MAIN/'worktrees/krn-024-20261105';BASE=IMPL/'artifacts/kernel-provider-link'
TIP='a8c45325356ed2842d34a8901fba92136564a397'
OUT=WT/'artifacts/rev-krn-024'/sys.argv[1];OUT.mkdir(parents=True,exist_ok=False)
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
commands,checks=[],[];resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(MAIN))
def passed(name,**kw):checks.append(dict(name=name,pass_check=True,**kw))
def run(label,argv):
    argv=[str(x) for x in argv];start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    p=subprocess.run(argv,cwd=WT,env=ENV,capture_output=True,timeout=45)
    a,b=OUT/(label+'.stdout'),OUT/(label+'.stderr');a.write_bytes(p.stdout);b.write_bytes(p.stderr)
    commands.append(dict(argv=argv,cwd=str(WT),exit_code=p.returncode,started_at=start,
       ended_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),stdout=rel(a),stderr=rel(b),
       environment={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE']}))
    assert p.returncode==0,(label,p.returncode,p.stderr[-2000:]);return p.stdout,p.stderr
def read(p):return json.loads(Path(p).read_text())
def ar_hashes(path):
    result=[]
    with path.open('rb') as f:
        assert f.read(8)==b'!<arch>\n'
        while head:=f.read(60):
            assert len(head)==60 and head[58:]==b'`\n'
            size=int(head[48:58]);name=head[:16].decode().strip();remaining=size
            if name.startswith('#1/'):
                n=int(name[3:]);name=f.read(n).rstrip(b'\0').decode();remaining-=n
            else:name=name.rstrip('/')
            h=hashlib.sha256()
            while remaining:
                b=f.read(min(65536,remaining));assert b;h.update(b);remaining-=len(b)
            if size&1:assert len(f.read(1))==1
            if not name.startswith('__.SYMDEF'):result.append((name,h.hexdigest()))
    return result
def renamed(data,kind):
    changed=bytearray(data);cursor=32
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,cursor)
        if command==0x19:
            n=struct.unpack_from('<I',data,cursor+64)[0]
            for i in range(n):
                pos=cursor+72+80*i;segment=data[pos+16:pos+32].rstrip(b'\0')
                flags=struct.unpack_from('<I',data,pos+64)[0]
                if flags&0x02000000:continue
                target=b'__HIB' if kind=='HIB' else b'__KLD' if segment==b'__TEXT' else b'__KLDDATA'
                changed[pos+16:pos+32]=target.ljust(16,b'\0')
        cursor+=size
    return bytes(changed)

report=dict(kind='source-review',origin='local-host',outcome='fail',commit=TIP,
 recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=commands,checks=checks,
 device_executed=False,summary='Independent current graph/native provider-link measurement review; no full link executed')
try:
    names=['tools/build/xnu_kernel_provider_link.py','docs/procedures/kernel-provider-link/verify.py',
       'docs/procedures/kernel-provider-link/README.md','fixtures/public/kernel-provider-link/qualified-measurement.json']
    for i,name in enumerate(names):
        data,_=run('exact-source-'+str(i),['git','-C',MAIN,'cat-file','blob',TIP+':'+name])
        assert data==(MAIN/name).read_bytes()==(IMPL/name).read_bytes()
    report['source_sha256']={n:sha(MAIN/n) for n in names}
    run('python-version',[sys.executable,'--version'])
    binding=read(BASE/'commit-binding/report.json');assert binding['commit']==TIP
    for name,row in binding['bindings'].items():
        assert sha(MAIN/name)==row['committed_sha256']==sha(MAIN/row['tested_snapshot'])==row['snapshot_sha256']
    passed('exact-candidate-four-source-files-and-real-precommit-snapshot-bindings')
    capsules={}
    for name in ['native-session1','native-session2','native-session3','acceptance-session1']:
        p=BASE/name/'evidence.json';doc=read(p)
        assert doc['outcome']==('fail' if name=='native-session1' else 'pass')
        for source,digest in doc['sha256'].items():assert sha(MAIN/source)==digest,source
        capsules[name]=dict(path=rel(p),sha256=sha(p),artifact_hash_entries=len(doc['sha256']))
    report['capsules']=capsules
    current=read(BASE/'native-session3/report.json');earlier=read(BASE/'native-session2/report.json')
    for p,h in current['tools_sha256'].items():assert sha(Path(p))==h,p
    assert len(current['checks'])==32 and all(c['pass_check'] for c in current['checks'])
    assert len(read(BASE/'acceptance-session1/report.json')['checks'])==23
    for command in current['commands']:
        assert sha(MAIN/command['stdout'])==command['stdout_sha256'] and sha(MAIN/command['stderr'])==command['stderr_sha256']
        assert hashlib.sha256(json.dumps(command['argv'],separators=(',',':')).encode()).hexdigest()==command['argv_sha256']
    passed('all-four-retained-capsules-and-all45-recorded-command-hashes',capsules=capsules)
    rows=read(BASE/'native-session3/current-compiled-objects.json');deps=read(BASE/'native-session3/current-dependency-files.json')
    historical={r['id']:r for r in read(MAIN/'artifacts/xnu-kernel-iig-objects/audit-session1/compiled-objects.json')}
    assert len(rows)==len({r['id'] for r in rows})==982 and len(deps)==3156
    assert {r['id'] for r in rows if r['output']!=historical[r['id']]['output']}=={'osfmk/caches_asm.o','osfmk/start.o','osfmk/model_dep.o','pexpert/pe_init.o'}
    kernel_defs=set();kernel_strong_imports=set();byid={r['id']:r for r in rows}
    hib={r['id'] for r in current['HIB_processing']};kld={r['id'] for r in current['KLD_processing']}
    assert len(hib)==14 and len(kld)==1
    for row in rows:
        assert sha(MAIN/row['source'])==row['source_sha256'] and sha(MAIN/row['output'])==row['output_sha256']
        data=(MAIN/row['output']).read_bytes();view=Object(data);kernel_defs.update(view.exported())
        imported_names=view.imported()
        kernel_strong_imports.update(s['name'] for s in view.symbols if s['name'] in imported_names and not s['description']&0x40)
        staged=current['staged_objects'][row['id']]
        assert staged['original']==row['output'] and staged['original_sha256']==row['output_sha256']
        actual=(MAIN/staged['output']).read_bytes()
        expected=renamed(data,'HIB' if row['id'] in hib else 'KLD') if row['id'] in hib|kld else data
        assert actual==expected and hashlib.sha256(actual).hexdigest()==staged['output_sha256']
    for p,h in deps.items():assert sha(MAIN/p)==h,p
    for p,h in current['source_inputs'].items():assert sha(MAIN/p)==h,p
    passed('actual982-object3156-dependency-graph-and-only-native-HIB-KLD-byte-transforms')
    stage=BASE/'native-session3/stage';ordered=[]
    for component in current['link_variables']['COMPONENT_LIST'].split():
        item=current['component_filelists'][component]
        paths=[str(stage/component/'RELEASE'/n) for n in item['objects']]
        assert (MAIN/item['path']).read_text().splitlines()==paths;ordered+=paths
    assert len(ordered)==978 and (MAIN/current['archive']['filelist']).read_text().splitlines()==ordered
    expected=[Path(p) for p in ordered]+[stage/n for n in current['archive']['tail']]
    actual=ar_hashes(MAIN/current['archive']['path'])
    assert len(actual)==len(expected)==981
    assert all(name==p.name and h==sha(p) for (name,h),p in zip(actual,expected))
    passed('streamed981-actual-native-archive-members-and978-filelist-order')
    aliaspath=stage/'all-alias.exp';aliases={b:a for line in aliaspath.read_text().splitlines() for a,b in [line.split()]}
    assert len(aliases)==83
    kernel=MAIN/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'
    export_files=[kernel/'config'/n for n in current['metadata']['query_values']['EXPORTS_FILES']]
    export_files += [Path(p) for key in ['Kasan_EXPORTS','Kcov_EXPORTS'] for p in current['metadata']['query_values'][key]]
    derived={line.split(':')[0].strip():line.split(':')[1].strip() for p in export_files for line in p.read_text().splitlines() if ':' in line}
    assert derived==aliases
    provider_defs=set();provider_imports=set();facts={}
    for name,item in current['providers'].items():
        assert sha(MAIN/item['archive'])==item['sha256']==sha(MAIN/item['original'])
        # Small provider archives are bounded; inspect their true member payloads.
        from object_reader import members
        definitions,imports=set(),set()
        for _,payload in members((MAIN/item['archive']).read_bytes()):
            view=Object(payload);definitions.update(view.exported());imports.update(view.imported())
        imports-=definitions
        assert sorted(definitions)==item['definitions'] and sorted(imports)==item['external_imports']
        assert not definitions&(kernel_defs|provider_defs)
        assert all(aliases.get(n,n) in kernel_defs for n in imports)
        provider_defs.update(definitions);provider_imports.update(imports)
        facts[name]=dict(definitions=len(definitions),imports=len(imports))
    remaining=sorted(n for n in kernel_strong_imports|provider_imports if aliases.get(n,n) not in kernel_defs|provider_defs)
    assert remaining==current['remaining_object_provider_names'] and len(remaining)==13
    passed('actual-provider-symbol-closure83-native-aliases-and13-linker-boundaries',providers=facts)
    missing=re.findall(r'^  "([^"]+)", referenced from:\n     -exported_symbol\[s_list\] command line option',earlier['actual_link']['diagnostic'],re.M)
    assert len(missing)==len(set(missing))==37
    mapping={}
    for name in missing:
        hits=[(str(p.relative_to(kernel)),i+1) for p in export_files for i,l in enumerate(p.read_text().splitlines()) if l.split(':',1)[0].strip()==name]
        assert len(hits)==1 and name not in kernel_defs|provider_defs;mapping[name]=hits[0]
    assert Counter(p for p,line in mapping.values())=={'config/Private.arm64.exports':35,'config/Private.exports':2}
    report['remaining_exports']=mapping
    passed('all37-earlier-errors-are-unique-absent-selected-export-list-names')
    policy=current['compiler_runtime_policy']
    for i,(name,item) in enumerate(policy['primary_sources'].items()):
        data,_=run('pinned-driver-'+str(i),['git','-C',MAIN/'references/xnu-tapi','cat-file','blob',item['revision']+':'+name])
        assert hashlib.sha256(data).hexdigest()==item['sha256']==sha(MAIN/item['compiler_source'])
    clang=MAIN/current['compiler']['path'];assert sha(clang)==current['compiler']['sha256']
    report['tool_sha256']={str(clang):sha(clang)}
    data,_=run('fresh-resource-dir',[clang,'-print-resource-dir'])
    assert data.decode().strip()==policy['resource_directory'] and not Path(policy['expected_runtime']).exists()
    original=current['driver_expansion'];data,stderr=run('fresh-real-driver-dry-run',[*original['compiler_argv'],'-###'])
    backend=[shlex.split(l) for l in stderr.decode().splitlines() if l.strip().startswith('"'+original['expanded_linker_argv'][0]+'"')]
    assert len(backend)==1 and backend[0]==original['expanded_linker_argv']
    direct=current['actual_link']['argv'].copy();direct.remove('-lcc_kext');assert direct==backend[0]
    assert [a for a in current['actual_link']['argv'] if a.startswith('-l')]==['-lcc_kext','-lfirehose_kernel','-lpthread_kext']
    assert current['actual_link']['exit_code']==1 and current['actual_link']['missing_cc_kext'] and not current['actual_link']['image_exists']
    assert not (MAIN/current['actual_link']['output']).exists()
    passed('fresh-source-backed-driver-omission-exact-single-argument-restoration-and-retained-failure')
    # Execute only pure validation methods on an uninitialized read-only instance.
    spec=importlib.util.spec_from_file_location('reviewed_link',MAIN/'tools/build/xnu_kernel_provider_link.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    obj=module.ProviderLink.__new__(module.ProviderLink)
    obj.root=MAIN;obj.stage=stage;obj.compiled=rows;obj.report=current;obj.aliases=aliases
    obj.pthread=read(MAIN/'fixtures/public/xnu-kernel-pthread-profile/qualified-component.json');obj.library=BASE/'native-session3/available-libraries'
    obj.validate_link(current['actual_link']['argv'])
    controls=[]
    for name,argv,kwargs in [('backend-library-omission',backend[0],{}),
      ('wrong-real-alias',current['actual_link']['argv'],{'aliases':dict(aliases,_mach_vm_map='_mach_vm_allocate_external')}),
      ('stale-real-graph',current['actual_link']['argv'],{'rows':list(historical.values())})]:
        try:obj.validate_link(argv,**kwargs)
        except ValueError as e:controls.append(dict(name=name,rejected=True,error=str(e)))
        else:raise AssertionError('Accepted wrong input: '+name)
    passed('three-fresh-actual-readonly-validator-rejections',controls=controls)
    assert all(current[k] is False for k in ['full_kernel_qualified','full_archive_link_qualified','full_crypto_qualified',
       'apple_private_abi_qualified','apple_interoperability_qualified','runtime_qualified','native_device_qualified','device_executed','sdk_used'])
    report['outcome']='pass'
except Exception as e:
    report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
    report['review_input_sha256']={str(p):sha(p) for p in [Path(__file__),HERE/'object_reader.py']}
    report['max_child_rss_kib']=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['max_harness_rss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['actual_process_VmHWM_kib']=int(re.search(r'^VmHWM:\s+(\d+) kB$',Path('/proc/self/status').read_text(),re.M)[1])
    report['rss_measurement_note']='Linux ru_maxrss can retain a pre-exec high-water mark; /proc/self VmHWM describes this actual process image.'
    report['limitations']=['No relink/build/target execution; original failures are retained measurements.',
       'Streaming archive audit, actual object/source checks and fresh dry-run/readonly controls only; no shared source/artifact mutation.',
       'Compiler runtime, crypto, export providers, full kernel/Apple ABI/runtime/native qualification remain separate gates.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    files=sorted(p for p in OUT.rglob('*') if p.is_file())
    evidence={k:report[k] for k in ['kind','origin','outcome','commit','recorded_at','commands','summary','device_executed']}
    evidence.update(artifacts=[rel(p) for p in files],sha256={rel(p):sha(p) for p in files})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),checks=checks,commands=len(commands),
       child_rss_kib=report['max_child_rss_kib'],harness_rss_kib=report['max_harness_rss_kib'],evidence=rel(OUT/'evidence.json')),indent=2))
sys.exit(0 if report['outcome']=='pass' else 1)
