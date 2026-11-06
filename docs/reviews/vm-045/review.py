"""Independent frozen VM045 source/metadata and temporary filesystem controls."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from types import ModuleType

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR = MAIN/'worktrees/vm-045-es-20261106'
BASE = Path(__file__).resolve().parent
OUT = BASE/'run-1'
Q = AUTHOR/'docs/procedures/avf-resource-namespace/guard-session3/qualification'
SOURCE_SHA = 'dd30589d316fbc5ebd64f8612a96a88247a9159152286a6200379106734b1e76'
FIXTURE_SHA = '9efbc366c01962300b02e6dea871d04c193555c232c649c3c4ca105e987315a6'
CAPSULE_SHA = '48591e4b0d8fb705221d7285df481d9ec77fcb32b8ebd27e5553bcd98ca35076'
DESCRIPTOR_SHA = 'eb2ca4400478800b4d72f5d231eb73f6d13c2ba41ffb477c28a07f5e6baff5a4'
checks = []
bindings = {}


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def canon(d):
    return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',', ':')).encode()).hexdigest()


def require(ok, label):
    if not ok: raise ValueError(label)


def positive(label, condition=True):
    require(condition,label)
    checks.append(dict(name=label,kind='positive',passed=True))


def pin(p,digest):
    p=Path(p)
    require(p.is_file() and not p.is_symlink() and sha(p)==digest,'Changed regular binding: '+str(p))
    bindings[str(p)]=digest
    return p


def read(p,digest=None):
    p=Path(p)
    pin(p,digest or sha(p))
    return json.loads(p.read_text())


def module(p,digest):
    pin(p,digest)
    m=ModuleType('review_'+p.stem);m.__file__=str(p)
    b=p.read_bytes();require(hashlib.sha256(b).hexdigest()==digest,'Module capture changed')
    exec(compile(b,str(p),'exec'),m.__dict__)
    return m


def negative(label,func,kind='producer-function'):
    try: func()
    except (ValueError,OSError) as e:
        checks.append(dict(name=label,kind=kind,rejected=True,diagnostic=str(e)))
    else: raise ValueError('Independent negative accepted: '+label)


def independent_rows(old,new,old_root,new_root):
    require(len(old)==len(new)==1080,'Wrong1080 cardinality')
    require([r['id']for r in old]==[r['id']for r in new],'Changed row order')
    deltas=[]
    for a,b in zip(old,new):
        aa={k:v for k,v in a.items() if k!='next_owned_compile_argv_template'}
        bb={k:v for k,v in b.items() if k!='next_owned_compile_argv_template'}
        require(aa==bb,'Changed non-argv fields: '+a['id'])
        x=a['next_owned_compile_argv_template'];y=b['next_owned_compile_argv_template']
        require(len(x)==len(y),'Changed argv length')
        for i,(u,v)in enumerate(zip(x,y)):
            if u!=v:
                require((a['id'],i,u,v)==('bsd/apfs_deflate.o',244,str(old_root),str(new_root)), 'Undeclared argv change')
                deltas.append((a['id'],i))
        if a['id']=='bsd/apfs_deflate.o': require(x[243]==y[243]=='-idirafter','Changed existing flag')
    require(deltas==[('bsd/apfs_deflate.o',244)],'Wrong exact delta')


def independent_namespace(parent,new,old_root,root,headers):
    expected=dict(roots=sorted(parent['roots']+[str(root)],key=lambda p:(len(Path(p).parts),p)),
        absent_search_roots=[p for p in parent['absent_search_roots']if p!=str(old_root)],
        files=dict(parent['files'],**{str(root/n):h for n,h in headers.items()}))
    require(new==dict(expected,sha256=canon(expected)),'Wrong namespace/parent closure')


def independent_index(parent,new):
    require(len(parent)==53997 and len(new)==54046,'Wrong index cardinality')
    require(all(new.get(p)==h for p,h in parent.items()),'Lost or changed parent index row')


def independent_key(row,manifest,ns):
    binding=dict(schema='avf-resource-namespace-v1',id=row['id'],manifest_sha256=manifest,
        namespace_sha256=ns,source=row['bound_source'],source_sha256=row['bound_source_sha256'],
        configuration=row['configuration'],configuration_sha256=row['configuration_sha256'],
        compiler=row['next_owned_compile_argv_template'][0],cwd=row['cwd'],
        argv_template_sha256=canon(row['next_owned_compile_argv_template']))
    return dict(id=row['id'],input_key=canon(binding),binding=binding)


def run():
    source=AUTHOR/'tools/build/avf_resource_namespace.py'
    m=module(source,SOURCE_SHA)
    inputs=read(AUTHOR/'fixtures/public/avf-resource-namespace/inputs.json',FIXTURE_SHA)
    helper=module(MAIN/inputs['parent_helper'],inputs['parent_helper_sha256'])
    descriptor=read(Q/'qualified-component.json',DESCRIPTOR_SHA)
    capsule=read(AUTHOR/'docs/procedures/avf-resource-namespace/evidence-session3.json',CAPSULE_SHA)
    require(capsule['outcome']=='pass','Producer capsule notpass')
    for p,h in capsule['sha256'].items():pin(MAIN/p,h)
    positive('producer-capsule-all-direct-bindings')
    for field in ['parents']:
        for obj in descriptor[field].values():pin(obj['path'],obj['sha256'])
    for field in ['object_manifest','selectors','namespace_receipt','object_input_keys','manifest_transition','artifact_index','source_proof','source_type_closure','consumer_contract']:
        obj=descriptor[field];pin(obj['path'],obj['sha256'])
    parents={n:read(MAIN/inputs[n],inputs[n+'_sha256'])for n in ['parent_manifest','parent_qualification','parent_namespace_receipt','parent_index','parent_selectors','parent_input_keys']}
    rows=parents['parent_manifest'];new=read(Q/'next-full-object-manifest.json')
    ns=read(Q/'input-bindings.json');parent_ns=parents['parent_namespace_receipt']
    old_root=Path(descriptor['old_root']['path']);root=Path(descriptor['new_root']['path']);headers=inputs['headers']
    historical_fh=MAIN/'worktrees/vm-008-20261105/artifacts/avf-kernel-headers/handoff-1/public-source-context/usr/local/include/kernel'
    absences=list(parent_ns['absent_search_roots'])+[str(historical_fh)]
    positive('all-parent-and-retired-historical-roots-absent-before',all(not os.path.lexists(p)for p in absences))
    independent_rows(rows,new,old_root,root)
    positive('independent-all1080-exact-operand-only-transition')
    positive('producer-transition-positive',len(m.validate_transition(helper,rows,new,old_root,root))==1080)
    positive('55-generated-inputs-preserved',sum(bool(r['generated_input'])for r in new)==55)
    independent_namespace(parent_ns,ns,old_root,root,headers)
    positive('independent-all6722-parent-files-plus3-namespace',len(ns['files'])==6725 and ns['sha256']==descriptor['namespace_digest'])
    index=read(Q/'artifact-index.json')['files'];parent_index=parents['parent_index']['files']
    independent_index(parent_index,index)
    delta={p:h for p,h in index.items()if p not in parent_index}
    positive('independent53997-verbatim-plus49-index',len(delta)==49)
    for p,h in delta.items():pin(MAIN/p,h)
    positive('49-new-index-witnesses-directly-hashed')
    normalized={str((MAIN/Path(p)).absolute()):h for p,h in index.items()}
    for p,h in ns['files'].items():require(normalized.get(p)==h,'Namespace missing in full index: '+p)
    positive('all6725-namespace-files-covered-by-complete-index')
    select=read(Q/'object-shards.json');expected=copy.deepcopy(parents['parent_selectors'])
    expected.update(source_manifest=str((Q/'next-full-object-manifest.json').relative_to(MAIN)),sha256=descriptor['object_manifest']['sha256'])
    positive('ten-ordered-selector-partitions-preserved',select==expected and len(select['shards'])==10)
    keys=read(Q/'object-input-keys.json')
    positive('independent1080-input-key-bindings',keys==dict(schema='avf-resource-namespace-v1',keys=[independent_key(r,descriptor['object_manifest']['sha256'],ns['sha256'])for r in new]))
    positive('all1080-previous-keys-retired',all(a['input_key']!=b['input_key']for a,b in zip(keys['keys'],parents['parent_input_keys']['keys'])))
    proof=read(Q/'canonical-resource-proof.json');tree=read(proof['canonical_git_tree']['path'],proof['canonical_git_tree']['sha256'])
    positive('canonical-tree-readonly-guard-flags',tree['exit_code']==0 and tree['stderr']=='' and tree['environment_overrides']['GIT_NO_LAZY_FETCH']=='1' and tree['environment_overrides']['GIT_OPTIONAL_LOCKS']=='0')
    blob_map={line.split('\t')[1]:line.split()[2]for line in tree['stdout'].splitlines()}
    for obj in proof['canonical_sources']:
        p=pin(obj['path'],obj['sha256']);b=p.read_bytes()
        require(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==obj['git_blob_sha1']==blob_map[obj['canonical_path']],'Canonical public blob mismatch')
    positive('ten-canonical-LLVM-source-blobs',len(proof['canonical_sources'])==10 and proof['source_revision']==inputs['source_revision'])
    for field in ['generation_report','compiler_report','final_compiler','generator','corrected_existing_flag_facts','actual_wave20_failure']:
        obj=proof[field];pin(obj['path'],obj['sha256'])
    generation=read(proof['generation_report']['path']);compiler=read(proof['compiler_report']['path'])
    positive('genuine-matching-compiler-resource-generation-parent',compiler['compiler_sha256']==inputs['compiler_sha256'] and compiler['source_revision']==generation['source_revision']==inputs['source_revision'] and compiler['resource_parent']['sha256']==inputs['generation_report_sha256'] and generation['resource_bundle']['headers']==headers)
    positive('historical-genuine-generator-commands',proof['generation_commands']==[c for c in generation['commands']if '-gen-arm-neon'in c['argv']or '-gen-arm-bf16'in c['argv']]and all(c['exit_code']==0 for c in proof['generation_commands']))
    for obj in proof['generation_depfiles']:
        pin(obj['path'],obj['sha256']);require(Path(obj['path']).read_text()==obj['text'],'Depfile text changed')
    facts=read(proof['corrected_existing_flag_facts']['path']);failed=read(proof['actual_wave20_failure']['path'])
    for field in ['previous_facts','actual_object_record','full_unfiltered_argv']:pin(MAIN/facts[field]['path'],facts[field]['sha256'])
    positive('actual-failure-and-corrected-existing-flag',failed['outcome']=='fail' and failed['command']['argv'][243:245]==['-idirafter',str(old_root)] and facts['exact_arguments']['resource_root_index']==244 and facts['actual_resource_root_exists']is False)
    for n,h in headers.items():
        pin(root/n,h);pin(MAIN/inputs['resource_source_root']/n,h)
    m.verify_resources(helper,root,headers)
    positive('exact-three-genuine-resource-bytes')
    closure=read(Q/'source-type-closure.json');selected=next(r for r in new if r['id']=='bsd/apfs_deflate.o')
    positive('producer-literal-closure-recomputed',m.closure(helper,selected,parent_ns,root,headers)==closure)
    roots=[];a=selected['next_owned_compile_argv_template'];i=1
    while i<len(a):
        token=a[i]
        if token in ['-I','-isystem','-idirafter','-iquote']:
            if token!='-iquote':roots.append(({'-I':0,'-isystem':1,'-idirafter':2}[token],str((Path(selected['cwd'])/a[i+1]).absolute())))
            i+=2;continue
        if token.startswith('-I')and len(token)>2:roots.append((0,str((Path(selected['cwd'])/token[2:]).absolute())))
        i+=1
    search=[p for _,p in sorted(roots,key=lambda x:x[0])]
    positive('independent-angle-precedence',search==[r['path']for r in closure['ordered_angle_search_roots']]and search[-1]==str(root))
    for node in closure['nodes']:
        obj=node['first_match'];pin(obj['path'],obj['sha256'])
        matches=[Path(p)/node['include']for p in search if (Path(p)/node['include']).is_file()]
        require(str(matches[0])==obj['path'],'Wrong first include: '+node['include'])
    positive('independent-source-firstmatch-prerequisites')
    contract=read(Q/'consumer-admission-contract.json')
    positive('no-consumer-execution-or-old-object-adoption',contract['actual_retry_authorized']is False and all(descriptor[k]is False for k in ['compiler_executed','generator_executed','old_objects_reused','actual_APFS_compile','sdk_qualified','private_abi_qualified']))
    # These are real producer primitive calls over actual frozen data, with
    # only one selected row copied for each mutation; no broad producer rerun.
    row_index=next(i for i,r in enumerate(new)if r['id']=='bsd/apfs_deflate.o')
    mutations={
        'wrong-resource-operand':lambda r:r['next_owned_compile_argv_template'].__setitem__(244,str(root.parent)),
        'generic-I-flag':lambda r:r['next_owned_compile_argv_template'].__setitem__(243,'-I'),
        'extra-include-token':lambda r:r['next_owned_compile_argv_template'].extend(['-I','/usr/include']),
        'late-profile-override':lambda r:r['next_owned_compile_argv_template'].append('-UDEVELOPMENT'),
        'wrong-compiler':lambda r:r['next_owned_compile_argv_template'].__setitem__(0,'/usr/bin/clang'),
        'wrong-source':lambda r:r.update(bound_source_sha256='0'*64),
        'wrong-configuration':lambda r:r.update(configuration_sha256='0'*64)}
    for label,mutate in mutations.items():
        changed=list(new);changed[row_index]=copy.deepcopy(new[row_index]);mutate(changed[row_index])
        negative(label,lambda:m.validate_transition(helper,rows,changed,old_root,root))
    changed=list(new);changed[0],changed[1]=changed[1],changed[0]
    negative('wrong-row-order',lambda:m.validate_transition(helper,rows,changed,old_root,root))
    bad=dict(ns,files=dict(ns['files']));bad['files'][str(root/'arm_neon.h')]='0'*64
    negative('wrong-namespace-header',lambda:helper.verify_namespace_exact(bad,ns))
    bad=dict(ns,files=dict(ns['files']));bad['files'].pop(next(iter(parent_ns['files'])))
    negative('dropped-parent-namespace-file',lambda:independent_namespace(parent_ns,bad,old_root,root,headers),'independent-oracle')
    bad_index=dict(index);bad_index.pop(next(iter(parent_index)))
    negative('dropped-parent-index-row',lambda:independent_index(parent_index,bad_index),'independent-oracle')
    negative('old-schema-input-key',lambda:require(parents['parent_input_keys']['keys'][row_index]==independent_key(selected,descriptor['object_manifest']['sha256'],ns['sha256']),'Old-profile key is not new key'),'independent-oracle')
    # Real owned temporary roots; no writes to author/parent/physical witness.
    controls=OUT/'controls';controls.mkdir()
    valid=controls/'valid';valid.mkdir()
    for n in headers:(valid/n).write_bytes((root/n).read_bytes())
    m.verify_resources(helper,valid,headers);positive('real-temp-three-header-root-positive')
    for label in ['changed','missing','shadow','symlink']:
        d=controls/label;d.mkdir()
        for n in headers:(d/n).write_bytes((root/n).read_bytes())
        if label=='changed':(d/'arm_neon.h').write_bytes(b'changed actual bytes')
        if label=='missing':(d/'arm_bf16.h').unlink()
        if label=='shadow':(d/'stdint.h').write_text('/* own shadow */\n')
        if label=='symlink':(d/'arm_neon.h').unlink();(d/'arm_neon.h').symlink_to(root/'arm_neon.h')
        negative('actual-temp-resource-'+label,lambda:m.verify_resources(helper,d,headers))
    alias=controls/'root-alias';alias.symlink_to(valid,target_is_directory=True)
    negative('actual-root-symlink',lambda:m.verify_resources(helper,alias,headers))
    for label,original in [('source',Path(proof['canonical_sources'][0]['path'])),('compiler',Path(proof['final_compiler']['path'])),('provenance',Path(proof['generation_report']['path']))]:
        p=controls/('changed-'+label);p.write_text('actual tampered '+label+'\n')
        negative('actual-'+label+'-pin',lambda:m.check_pin(p,sha(original)))
    present=controls/'materialized-old-root';present.mkdir()
    negative('actual-owned-materialized-absence',lambda:m.require_absent([present]))
    dangling=controls/'dangling-absent-alias';dangling.symlink_to(controls/'nonexistent')
    negative('actual-dangling-absence',lambda:m.require_absent([dangling]))
    negative('out-of-scope-output',lambda:m.output_path(BASE/'escape'))
    negative('unowned-symlink-output',lambda:m.output_path(alias/'fresh'))
    positive('producer-owned-output-positive',m.output_path(Q/'never-created-review-probe')==Q/'never-created-review-probe')
    # Retain exact failed source experiments and original physical hashes.
    for name in ['evidence.json','evidence-session2.json']:
        obj=read(AUTHOR/'docs/procedures/avf-resource-namespace'/name)
        positive('preserved-source-failure-'+name,obj['outcome']=='fail')
        for p,h in obj.get('sha256',{}).items():pin(MAIN/p,h)
    positive('all-parent-and-retired-historical-roots-absent-after',all(not os.path.lexists(p)for p in absences))
    for p,h in list(bindings.items()):pin(p,h)
    positive('all-direct-bindings-unchanged-after')
    return dict(producer_commit='75f09b8035b5d19022da5cb191d0b4ea5b05561f',source_sha256=SOURCE_SHA,
        descriptor_sha256=DESCRIPTOR_SHA,parent_physical_corpus_rehashed=False,parent_index_entries=53997,
        new_index_entries=54046,new_index_delta_hashed=49,namespace_files=6725,ordered_rows=1080,
        input_keys=1080,absent_paths_observed=absences,subprocesses_from_review_child=0)


if __name__=='__main__':
    result=dict(recorded_at=datetime.now(timezone.utc).isoformat(),kind='host-test',origin='local-host',outcome='fail')
    code=1
    try:
        result.update(run());result['outcome']='pass';code=0
    except Exception as error:
        result.update(error_type=type(error).__name__,error=str(error))
    finally:
        result.update(checks=checks,checks_total=len(checks),negative_controls=sum(c.get('rejected',False)for c in checks),bindings=bindings,
            proc_status=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))],
            compiler_executed=False,generator_executed=False,guest_executed=False,consumer_admitted=False)
        (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({k:result[k]for k in ['outcome','checks_total','negative_controls']},indent=2))
    sys.exit(code)
