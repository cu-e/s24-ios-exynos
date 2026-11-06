"""Focused independent exact-profile/source review, no target execution."""
import ast
import copy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import ModuleType,SimpleNamespace

MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR=MAIN/'worktrees/vm-046-ev-20261106'
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
OUT=BASE/'run-1'
TOOL=AUTHOR/'tools/build/avf_kernel_objects.py'
BASELINE=MAIN/'worktrees/vm-044-ep-fix5-20261106/tools/build/avf_kernel_objects.py'
NEW='9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
OLD='bfa8a7ddc2d0d9fa42158c24d9d3906a26348666e82b2fcae181e72763911dc3'
checks=[];bindings={};commands=[]


def sha(p):
    with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()


def need(ok,message):
    if not ok:raise ValueError(message)


def check(label,ok=True):
    need(ok,label);checks.append(dict(name=label,passed=True))


def pin(p,h):
    p=Path(p);need(p.is_file()and not p.is_symlink()and sha(p)==h,'Changed regular binding: '+str(p));bindings[str(p)]=h;return p


def read(p,h=None):
    p=Path(p);pin(p,h or sha(p));return json.loads(p.read_text())


def module(p,h):
    pin(p,h);b=p.read_bytes();need(hashlib.sha256(b).hexdigest()==h,'Module capture changed')
    m=ModuleType('frozen_'+p.stem);m.__file__=str(p);exec(compile(b,str(p),'exec'),m.__dict__);return m


def reject(label,action):
    try:action()
    except (ValueError,OSError,KeyError,TypeError)as error:checks.append(dict(name=label,rejected=True,diagnostic=str(error)))
    else:raise ValueError('Negative accepted: '+label)


def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')


def ast_checks():
    old=ast.parse(pin(BASELINE,OLD).read_bytes());new=ast.parse(pin(TOOL,NEW).read_bytes())
    nodes=lambda t:{n.name:n for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    a=nodes(old);b=nodes(new);changed={'accepted_profile','bind','task_shards','main'}
    check('only-one-new-function',set(b)-set(a)=={'resource_profile'}and not(set(a)-set(b)))
    for name,node in a.items():
        if name not in changed:check('BFA8-AST-unchanged-'+name,ast.dump(node)==ast.dump(b[name]))
    norm=copy.deepcopy(b['accepted_profile'])
    added=[n for n in norm.body if isinstance(n,ast.If)and 'RESOURCE_MANIFEST'in ast.unparse(n.test)]
    need(len(added)==1,'Exactly one third tuple branch');norm.body.remove(added[0]);norm.body[-1]=copy.deepcopy(a['accepted_profile'].body[-1])
    check('prior-profile-branches-byte-semantics-unchanged',ast.dump(norm)==ast.dump(a['accepted_profile']))
    norm=copy.deepcopy(b['bind']);dispatch=next(n for n in norm.body if isinstance(n,ast.If)and ast.unparse(n.test)=="'schema' in profile")
    original=next(n for n in a['bind'].body if isinstance(n,ast.If)and ast.unparse(n.test)=="'schema' in profile")
    check('bind-only-resource-dispatch',len(dispatch.body)==2 and ast.unparse(dispatch.body[0])=="validator = resource_profile if profile['schema'] == RESOURCE_SCHEMA else firehose_profile" and ast.unparse(dispatch.body[1])=='qualified, profile_keys, profile_namespace = validator(args, rows, qualified)')
    dispatch.body=copy.deepcopy(original.body);check('all-other-bind-AST-unchanged',ast.dump(norm)==ast.dump(a['bind']))
    norm=copy.deepcopy(b['task_shards']);branch=next(n for n in norm.body if isinstance(n,ast.If)and ast.unparse(n.test)=="task['id'] == 'VM-046'");norm.body.remove(branch)
    check('all-prior-task-authority-AST-unchanged',ast.dump(norm)==ast.dump(a['task_shards']))
    norm=copy.deepcopy(b['main']);branch=next(n for n in norm.body if isinstance(n,ast.If)and ast.unparse(n.test)=='args.manifest_sha256 == RESOURCE_MANIFEST')
    position=norm.body.index(branch);need(ast.unparse(branch.body[0])=='accepted_profile(args)'and len(branch.body)==1,'Only exact preflight call')
    check('explicit-policy-preflight-before-owned-mkdir',ast.unparse(norm.body[position+1])=='out = owned_out(args)')
    norm.body.remove(branch);check('all-main-runtime-budget-cleanup-AST-unchanged',ast.dump(norm)==ast.dump(a['main']))
    globals_only=lambda t:[n for n in t.body if not isinstance(n,(ast.FunctionDef,ast.ClassDef))and not(isinstance(n,ast.Assign)and any(isinstance(v,ast.Name)and v.id.startswith('RESOURCE_')for v in n.targets))]
    check('all-nonprofile-module-statements-AST-unchanged',ast.dump(ast.Module(body=globals_only(old),type_ignores=[]))==ast.dump(ast.Module(body=globals_only(new),type_ignores=[])))


def run():
    ast_checks();e=module(TOOL,NEW)
    capsule=read(AUTHOR/'docs/procedures/avf-resource-profile/evidence.json','53db0daadc1c58add8e9d03fd9150de2ef4390424833eb2325edf39a868177b8')
    for p,h in capsule['sha256'].items():pin(MAIN/p,h)
    raw=read(MAIN/capsule['raw_capsule'],capsule['raw_capsule_sha256'])
    check('actual-completed-producer89-controls',capsule['outcome']==raw['outcome']=='pass'and len(raw['checks'])==89 and all(c.get('pass')for c in raw['checks']))
    for p,h in raw.get('artifact_hashes',{}).items():pin(p,h)
    check('all-producer-recorded-outputs-unchanged')
    fixture=read(AUTHOR/'fixtures/public/avf-resource-profile/inputs.json','8946b29eb8760c1224b5f8a84b67cdb4f0cfb83811f5cdcc35c518fd4877009c')
    profile=fixture['profile'];q=read(profile['qualification']['path'],profile['qualification']['sha256']);rows=read(profile['manifest']['path'],profile['manifest']['sha256'])
    args=SimpleNamespace(main=MAIN,manifest=Path(profile['manifest']['path']),qualification=Path(profile['qualification']['path']),selectors=Path(profile['selectors']['path']),resource_profile=e.PROJECT_PROFILE,**{n+'_sha256':profile[n]['sha256']for n in ['manifest','qualification','selectors']})
    check('exact-third-tuple-positive',e.accepted_profile(args)==dict(manifest_sha256=e.RESOURCE_MANIFEST,namespace_sha256=e.RESOURCE_NAMESPACE,schema=e.RESOURCE_SCHEMA))
    for field in ['manifest_sha256','qualification_sha256','selectors_sha256']:
        bad=copy.copy(args);setattr(bad,field,'0'*64);reject('tuple-'+field,lambda:e.accepted_profile(bad))
    for policy in ['legacy','unrecognized',None]:
        bad=copy.copy(args);bad.resource_profile=policy;reject('resource-policy-'+str(policy),lambda:e.accepted_profile(bad))
    bad=copy.copy(args);del bad.resource_profile;reject('missing-explicit-resource-policy',lambda:e.accepted_profile(bad))
    for label,triple,expected in [('legacy',(e.PIN,e.LEGACY_QUALIFICATION,e.LEGACY_SELECTORS),dict(manifest_sha256=e.PIN,namespace_sha256=e.LEGACY_NAMESPACE)),('firehose',(e.FIREHOSE_MANIFEST,e.FIREHOSE_QUALIFICATION,e.FIREHOSE_SELECTORS),dict(manifest_sha256=e.FIREHOSE_MANIFEST,namespace_sha256=e.FIREHOSE_NAMESPACE,schema=e.FIREHOSE_SCHEMA))]:
        bad=copy.copy(args);bad.manifest_sha256,bad.qualification_sha256,bad.selectors_sha256=triple
        check('prior-'+label+'-tuple-positive',e.accepted_profile(bad)==expected)
    # One real full-metadata admission, deliberately no bind()/full corpus scan.
    qualified,keymap,ns=e.resource_profile(args,rows,q)
    expected_keys=read(profile['keys']['path'],profile['keys']['sha256'])['keys']
    check('actual-resource-profile-full1080-positive',len(keymap)==1080 and keymap=={x['id']:x for x in expected_keys}and ns==read(profile['namespace_receipt']['path'],profile['namespace_receipt']['sha256']))
    check('profile-qualified-index-bound',qualified['artifact_index_sha256']==profile['index']['sha256']and len(ns['files'])==6725)
    del qualified,keymap,ns
    # Recorded actual plans independently compared, no successful CLI rerun.
    producer_out=AUTHOR/'artifacts/avf-resource-profile/frozen-001'
    prior=MAIN/'worktrees/vm-039-ej-20261106/artifacts/avf-guest-profile/frozen-001'
    for label in ['legacy-plan','firehose-plan']:
        newer=producer_out/label;older=prior/label
        check(label+'-prior-full-plan-bytes', (newer/'execution-plan.json').read_bytes()==(older/'execution-plan.json').read_bytes().replace(str(older).encode(),str(newer).encode()))
        check(label+'-prior-input-bytes',(newer/'input-bindings.json').read_bytes()==(older/'input-bindings.json').read_bytes())
        plan=read(newer/'execution-plan.json');evidence=read(newer/'evidence.json')
        check(label+'-real-plan-no-compiler',len(plan['selected'])==23 and evidence['compiler_started']is False and evidence['outcome']=='pass')
    plan=read(producer_out/'resource-plan/execution-plan.json');evidence=read(producer_out/'resource-plan/evidence.json')
    keymap={x['id']:x['input_key']for x in expected_keys}
    check('recorded-real-BSD90-plan-with-exact-keys',len(plan['selected'])==90 and evidence['compiler_started']is False and plan['source_profile']['schema']==e.RESOURCE_SCHEMA and all(x['input_key']==keymap[x['id']]for x in plan['selected']))
    root=Path(q['new_root']['path']);oldroot=Path(q['old_root']['path']);apfs=next(x for x in plan['selected']if x['id']=='bsd/apfs_deflate.o')
    check('recorded-APFS-original-flag-and-only-new-root',apfs['argv'][243:245]==['-idirafter',str(root)])
    for label in ['legacy-plan','firehose-plan']:
        oldplan=read(producer_out/label/'execution-plan.json');reject('cross-profile-resume-'+label,lambda:e.resume_profile(dict(provenance=oldplan['provenance']),plan))
    e.resume_profile(dict(provenance=plan['provenance']),plan);check('same-profile-resume-policy-preserved')
    task=dict(id='VM-046',paths=['tools/build/avf_kernel_objects.py','fixtures/public/avf-resource-profile','docs/procedures/avf-resource-profile'])
    check('literal046-plan-only',e.task_shards(task,'plan','bsd-filesystems')==dict(authorized_shards=[],source_only_tooling_exception=True))
    reject('literal046-execute-prohibited',lambda:e.task_shards(task,'execute','bsd-filesystems'))
    for paths in [task['paths'][:-1],task['paths']+['docs/procedures/avf-object-shards/bsd-filesystems']]:reject('wrong046-literal-scope-'+str(len(paths)),lambda:e.task_shards(dict(task,paths=paths),'plan','bsd-filesystems'))
    reject('reviewer-scope-not-shard-authority',lambda:e.task_shards(dict(id='REV-042',paths=['docs/reviews/vm-046']),'execute','bsd-filesystems'))
    controls=OUT/'controls';controls.mkdir()
    # Test consumer semantic checks with freshly bound owned malformed files.
    def mutated(field,value):
        p=controls/(field+'.json');dump(p,value);bad=copy.deepcopy(q);bad[field]=dict(path=str(p),sha256=sha(p));return bad
    bad=copy.deepcopy(q);bad['namespace_digest']='0'*64;reject('wrong-namespace-digest',lambda:e.resource_profile(args,rows,bad))
    bad=copy.deepcopy(q);bad['source_proof']['sha256']='0'*64;reject('wrong-source-proof-pin',lambda:e.resource_profile(args,rows,bad))
    bad=copy.deepcopy(q);bad['parents']['parent_index']['sha256']='0'*64;reject('wrong-parent-index-pin',lambda:e.resource_profile(args,rows,bad))
    bad=copy.deepcopy(q);bad['new_root']['files']['arm_bf16.h']='0'*64;reject('wrong-resource-byte-pin',lambda:e.resource_profile(args,rows,bad))
    bad=copy.deepcopy(q);bad['new_root']['path']=str(root.parent);reject('wrong-canonical-resource-slot',lambda:e.resource_profile(args,rows,bad))
    receipt=read(profile['namespace_receipt']['path']);receipt['files'].pop(next(iter(receipt['files'])))
    bad=mutated('namespace_receipt',receipt);reject('fully-rebound-dropped-namespace',lambda:e.resource_profile(args,rows,bad));del receipt
    index=read(profile['index']['path']);index['files'].pop(next(iter(index['files'])))
    bad=mutated('artifact_index',index);reject('fully-rebound-dropped-parent-index',lambda:e.resource_profile(args,rows,bad));del index
    keys=read(profile['keys']['path']);keys['schema']=e.FIREHOSE_SCHEMA
    bad=mutated('object_input_keys',keys);reject('fully-rebound-old-key-schema',lambda:e.resource_profile(args,rows,bad));del keys
    contract=read(profile['consumer_contract']['path']);contract['actual_retry_authorized']=True
    bad=mutated('consumer_contract',contract);reject('fully-rebound-forged-retry-authority',lambda:e.resource_profile(args,rows,bad))
    idx=next(i for i,r in enumerate(rows)if r['id']=='bsd/apfs_deflate.o')
    for label,change in [('flag',lambda r:r['next_owned_compile_argv_template'].__setitem__(243,'-I')),('root',lambda r:r['next_owned_compile_argv_template'].__setitem__(244,str(root.parent))),('source',lambda r:r.update(bound_source_sha256='0'*64)),('profile',lambda r:r['next_owned_compile_argv_template'].append('-UDEVELOPMENT'))]:
        badrows=list(rows);badrows[idx]=copy.deepcopy(rows[idx]);change(badrows[idx]);reject('consumer-rejects-changed-'+label,lambda:e.resource_profile(args,badrows,q))
    reject('consumer-rejects-row-order',lambda:e.resource_profile(args,rows[::-1],q))
    # Fake MAIN copies prove actual captured-source pins; no global overrides.
    fake=controls/'fake-main';(fake/'tools/build').mkdir(parents=True)
    (fake/'tools/build/avf_resource_namespace.py').write_text('# changed actual source\n')
    badargs=copy.copy(args);badargs.main=fake
    reject('actual-modified-resource-validator-source',lambda:e.resource_profile(badargs,rows,q))
    (fake/'tools/build/avf_resource_namespace.py').write_bytes((MAIN/'tools/build/avf_resource_namespace.py').read_bytes())
    (fake/'tools/build/avf_firehose_namespace.py').write_text('# changed actual parent source\n')
    reject('actual-modified-transitive-parent-validator',lambda:e.resource_profile(badargs,rows,q))
    # Real tiny local namespace/root/absence controls avoid corpus replay.
    pure=module(MAIN/'tools/build/avf_resource_namespace.py','dd30589d316fbc5ebd64f8612a96a88247a9159152286a6200379106734b1e76');fh=e.profile_rules(MAIN)
    local=controls/'resource';local.mkdir()
    for n in q['new_root']['files']:(local/n).write_bytes((root/n).read_bytes())
    pure.verify_resources(fh,local,q['new_root']['files']);check('actual-local-three-header-positive')
    fake_row=dict(cwd=str(local),bound_source=str(local/'arm_bf16.h'),next_owned_compile_argv_template=['-I',str(local)])
    local_index={str(local/n):h for n,h in q['new_root']['files'].items()}
    e.namespace([fake_row],local_index,e.Digests());check('actual-local-full-namespace-positive')
    extra=local/'stdint.h';extra.write_text('shadow\n');reject('actual-shadow-root',lambda:pure.verify_resources(fh,local,q['new_root']['files']));reject('actual-new-namespace-shadow',lambda:e.namespace([fake_row],local_index,e.Digests()));extra.unlink()
    header=local/'arm_bf16.h';saved=header.read_bytes();header.write_bytes(saved+b'\n');reject('actual-changed-header',lambda:pure.verify_resources(fh,local,q['new_root']['files']));header.unlink();reject('actual-missing-header',lambda:pure.verify_resources(fh,local,q['new_root']['files']));header.symlink_to(root/'arm_bf16.h');reject('actual-header-symlink',lambda:pure.verify_resources(fh,local,q['new_root']['files']));header.unlink();header.write_bytes(saved)
    alias=controls/'alias';alias.symlink_to(local,target_is_directory=True);reject('actual-root-ancestry-symlink',lambda:e.canonical_output_path(alias));alias.unlink()
    absent=controls/'absent';pure.require_absent([absent]);absent.mkdir();reject('actual-absence-materialization',lambda:pure.require_absent([absent]))
    # Actual CLI refusals using ONLY this review's own task/owner/experiment.
    for label,policy,mixed,mode,diagnostic in [('missing-policy',False,False,'plan','requires explicit project-budget-v1'),('mixed-tuple',True,True,'plan','Only the three exact'),('reviewer-plan-authority',True,False,'plan','not reserved by both literal'),('reviewer-execute-authority',True,False,'execute','not reserved by both literal')]:
        target=OUT/('cli-'+label)
        argv=[sys.executable,'-B','-s',str(TOOL),'--main',str(MAIN),'--task','REV-042','--owner','codex-review-resource-profile-20261106-ew','--experiment','REV046EW-001','--shard','bsd-filesystems','--mode',mode,'--out',str(target)]
        for n in ['manifest','qualification','selectors']:argv+=['--'+n,profile[n]['path'],'--'+n+'-sha256','0'*64 if mixed and n=='qualification'else profile[n]['sha256']]
        if policy:argv+=['--resource-profile',e.PROJECT_PROFILE]
        result=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=15,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1'))
        (OUT/(label+'.stdout')).write_bytes(result.stdout);(OUT/(label+'.stderr')).write_bytes(result.stderr)
        commands.append(dict(argv=argv,cwd=str(ROOT),exit_code=result.returncode,stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),output_created=target.exists(),timeout_seconds=15))
        check('actual-CLI-'+label+'-refuses-before-mkdir',result.returncode!=0 and not target.exists()and diagnostic in result.stderr.decode())
    check('historical-absence-unchanged',not os.path.lexists(oldroot))
    for p,h in list(bindings.items()):pin(p,h)
    check('all-recorded-bindings-unchanged-after')
    return dict(existing_runtime_AST_preserved=True,whole_parent_corpus_rehashed=False,producer_suite_repeated=False,compiler_started=False,actual_allocation_granted=False)


if __name__=='__main__':
    record=dict(kind='host-test',origin='local-host',recorded_at=datetime.now(timezone.utc).isoformat(),outcome='fail');code=1
    try:record.update(run());record['outcome']='pass';code=0
    except Exception as error:record.update(error_type=type(error).__name__,error=str(error))
    finally:
        record.update(checks=checks,checks_total=len(checks),negative_controls=sum(x.get('rejected',False)for x in checks),bindings=bindings,commands=commands,proc_status=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))]);dump(OUT/'report.json',record);print(json.dumps({k:record[k]for k in ['outcome','checks_total','negative_controls']},indent=2))
    sys.exit(code)
