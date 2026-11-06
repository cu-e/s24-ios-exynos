#!/usr/bin/env python3
"""Bounded genuine source-only plans and matching-resource admission controls."""
import argparse
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]; TOOL=ROOT/'tools/build/avf_kernel_objects.py'
spec=importlib.util.spec_from_file_location('resource_consumer',TOOL);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--main',type=Path,required=True);parser.add_argument('--experiment',required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.main=args.main.resolve();out=args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():raise ValueError('Fresh own artifact output required')
    out.mkdir(parents=True);checks=[];commands=[]
    report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':e.stamp(),'argv':[sys.executable,*sys.argv],'checks':checks,'commands':commands,'compiler_started':False,'guest_executed':False,'full_common_run':False}
    def check(name,value):
        checks.append({'name':name,'pass':bool(value)})
        if not value:raise ValueError('Control failed: '+name)
    def rejects(name,call):
        try:call()
        except (ValueError,KeyError,OSError,TypeError) as error:checks.append({'name':name,'pass':True,'rejection':repr(error)})
        else:raise ValueError('Invalid admission accepted: '+name)
    try:
        supervise=e.supervisor(args.main);admission=[]
        for n in range(3):
            if n:time.sleep(1)
            sample=supervise.sample();admission.append(sample)
        report['admission']=admission
        if any(s['MemAvailable_bytes']<4*e.GIB or supervise.pressured(s) for s in admission):report['outcome']='resource-deferred';return 2
        config=e.load(ROOT/'fixtures/public/avf-resource-profile/inputs.json');current=config['profile']
        accepted=(args.main/'worktrees/vm-044-ep-fix5-20261106/tools/build/avf_kernel_objects.py').read_bytes()
        check('physical final BFA8 source exact',e.sha(args.main/'worktrees/vm-044-ep-fix5-20261106/tools/build/avf_kernel_objects.py')==config['accepted_budget_sha256'])
        def nodes(raw):return {n.name:n for n in ast.parse(raw).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
        old_nodes=nodes(accepted);new_nodes=nodes(TOOL.read_bytes());changed={'accepted_profile','bind','task_shards','main'}
        for name in old_nodes:
            if name not in changed:check('accepted BFA8 AST unchanged '+name,ast.dump(old_nodes[name])==ast.dump(new_nodes[name]))
        initial=copy.deepcopy(new_nodes['main']);initial.body=[n for n in initial.body if not (isinstance(n,ast.If) and ast.unparse(n.test)=='args.manifest_sha256 == RESOURCE_MANIFEST')]
        check('main budget/execution body unchanged except resource preflight before mkdir',ast.dump(initial)==ast.dump(old_nodes['main']))
        task={'id':'VM-046','paths':['tools/build/avf_kernel_objects.py','fixtures/public/avf-resource-profile','docs/procedures/avf-resource-profile']}
        check('exact046 tooling permits source-only plans',e.task_shards(task,'plan','bsd-filesystems')['source_only_tooling_exception'])
        rejects('046 tooling cannot execute',lambda:e.task_shards(task,'execute','bsd-filesystems'))
        rejects('046 incomplete literal scope cannot plan',lambda:e.task_shards(dict(task,paths=task['paths'][:-1]),'plan','bsd-filesystems'))
        old=e.load(args.main/'fixtures/public/avf-kernel-objects/inputs.json')
        fhbase=args.main/'worktrees/vm-038-20261106/docs/procedures/avf-firehose-namespace/qualification-session1'
        firehose={name:{'path':str(fhbase/file),'sha256':digest} for name,file,digest in [('manifest','next-full-object-manifest.json',e.FIREHOSE_MANIFEST),('qualification','qualified-component.json',e.FIREHOSE_QUALIFICATION),('selectors','object-shards.json',e.FIREHOSE_SELECTORS)]}
        pins={name:current[name] for name in ['manifest','qualification','selectors']};plans={}
        def cli(label,pins,shard='security',project=True,owner='codex-guest-resource-profile-20261106-ev',mode='plan'):
            target=out/label;argv=[sys.executable,TOOL,'--mode',mode,'--main',args.main,'--task','VM-046','--owner',owner,'--experiment',args.experiment,'--shard',shard,'--out',target]
            for name,item in pins.items():argv.extend(['--'+name,item['path'],'--'+name+'-sha256',item['sha256']])
            if project:argv.extend(['--resource-profile',e.PROJECT_PROFILE])
            result=e.run_child(argv,ROOT,out,label,supervise,timeout=120,admit=False);commands.append(result);return target,result
        for label,p,shard,project,count in [('legacy-plan',old,'security',False,23),('firehose-plan',firehose,'security',True,23),('resource-plan',pins,'bsd-filesystems',True,90)]:
            target,result=cli(label,p,shard,project)
            check(label+' actual source-only CLI exits0',result['outcome']=='pass')
            plan=e.load(target/'execution-plan.json');evidence=e.load(target/'evidence.json');plans[label]=plan
            check(label+' genuine selected recipes bound without compiler',evidence['outcome']=='pass' and evidence['compiler_started'] is False and len(plan['selected'])==count)
        prior=args.main/'worktrees/vm-039-ej-20261106/artifacts/avf-guest-profile/frozen-001'
        for label in ['legacy-plan','firehose-plan']:
            old_path=prior/label
            check(label+' exact old plan bytes except owned output prefix',(out/label/'execution-plan.json').read_bytes()==(old_path/'execution-plan.json').read_bytes().replace(str(old_path).encode(),str(out/label).encode()))
            check(label+' complete input binding bytes unchanged',(out/label/'input-bindings.json').read_bytes()==(old_path/'input-bindings.json').read_bytes())
        for label,p,project,owner,mode in [('no-resource-profile',pins,False,'codex-guest-resource-profile-20261106-ev','plan'),('wrong-owner',pins,True,'unowned-control','plan'),('tooling-execution',pins,True,'codex-guest-resource-profile-20261106-ev','execute')]:
            target,result=cli(label,p,project=project,owner=owner,mode=mode)
            check(label+' actual CLI refuses before mkdir/child compiler',result['outcome']=='fail' and not target.exists())
        bad=copy.deepcopy(pins);bad['qualification']['sha256']='0'*64;target,result=cli('mixed-tuple',bad)
        check('mixed tuple actual CLI refuses before mkdir',result['outcome']=='fail' and not target.exists())
        profile_args=SimpleNamespace(main=args.main,manifest=Path(pins['manifest']['path']),qualification=Path(pins['qualification']['path']),selectors=Path(pins['selectors']['path']),resource_profile=e.PROJECT_PROFILE,**{n+'_sha256':p['sha256'] for n,p in pins.items()})
        for name in ['manifest_sha256','qualification_sha256','selectors_sha256']:
            changed=copy.copy(profile_args);setattr(changed,name,'0'*64);rejects('exact tuple refuses wrong '+name,lambda:e.accepted_profile(changed))
        descriptor=e.load_project(pins['qualification']['path'],e.RESOURCE_QUALIFICATION);rows=e.load_project(pins['manifest']['path'],e.RESOURCE_MANIFEST);parents=descriptor['parents'];old_rows=e.load_project(parents['parent_manifest']['path'],e.FIREHOSE_MANIFEST)
        old_root=Path(descriptor['old_root']['path']);root=Path(descriptor['new_root']['path']);fh=e.profile_rules(args.main)
        raw=(args.main/'tools/build/avf_resource_namespace.py').read_bytes();check('accepted pure resource validator captured bytes exact',e.sha(args.main/'tools/build/avf_resource_namespace.py')==config['producer']['source']['sha256'])
        rspec=importlib.util.spec_from_file_location('resource_pure_controls',args.main/'tools/build/avf_resource_namespace.py');r=importlib.util.module_from_spec(rspec);exec(compile(raw,str(args.main/'tools/build/avf_resource_namespace.py'),'exec'),r.__dict__)
        transitions=r.validate_transition(fh,old_rows,rows,old_root,root)
        check('exact one same-slot resource operand changes across1080 rows',[(x['id'],v['argv_index']) for x in transitions for v in x['replacements']]==[('bsd/apfs_deflate.o',244)] and sum(x['generated_input'] is True for x in rows)==55)
        keys=e.load_project(descriptor['object_input_keys']['path'],descriptor['object_input_keys']['sha256'])['keys'];expected=[r.object_key(row,e.RESOURCE_MANIFEST,e.RESOURCE_NAMESPACE) for row in rows];keymap={x['id']:x['input_key'] for x in keys}
        check('all1080 exact resource keys recomputed',keys==expected)
        parent_keys=e.load_project(fhbase/'object-input-keys.json','51af75ee003db45033b9079922afa54808ee83c1e9751b77a63a15f51e4be606')['keys']
        check('no automatic old key credit across any1080 rows',all(a['id']==b['id'] and a['input_key']!=b['input_key'] for a,b in zip(keys,parent_keys)))
        plan=plans['resource-plan'];apfs=next(x for x in plan['selected'] if x['id']=='bsd/apfs_deflate.o')
        check('actual BSD90 plan binds resource tuple and APFS existing slot',plan['resource_profile']==e.PROJECT_PROFILE and plan['source_profile']['schema']==e.RESOURCE_SCHEMA and plan['provenance']['namespace_sha256']==e.RESOURCE_NAMESPACE and apfs['argv'][243:245]==['-idirafter',str(root)] and all(x['input_key']==keymap[x['id']] for x in plan['selected']))
        for prior_plan in [plans['legacy-plan'],plans['firehose-plan']]:rejects('cross-profile resume '+prior_plan['source_profile']['schema'] if 'source_profile' in prior_plan else 'legacy cross-profile resume',lambda:e.resume_profile({'provenance':prior_plan['provenance']},plan))
        e.resume_profile({'provenance':plan['provenance']},plan);check('same-profile resume identity remains allowed',True)
        for name,mutate in [('source',lambda row:row.update(bound_source_sha256='0'*64)),('config',lambda row:row.update(configuration_sha256='0'*64)),('flag',lambda row:row['next_owned_compile_argv_template'].__setitem__(243,'-I')),('wrong-root-slot',lambda row:row['next_owned_compile_argv_template'].__setitem__(244,str(root.parent))),('extra-flag',lambda row:row['next_owned_compile_argv_template'].extend(['-I','/usr/include']))]:
            changed=rows.copy();idx=next(i for i,x in enumerate(rows) if x['id']=='bsd/apfs_deflate.o');changed[idx]=copy.deepcopy(rows[idx]);mutate(changed[idx]);rejects('transition refuses changed '+name,lambda:r.validate_transition(fh,old_rows,changed,old_root,root))
        changed=rows[::-1];rejects('transition refuses ordered row change',lambda:r.validate_transition(fh,old_rows,changed,old_root,root))
        sandbox=out/'controls';sandbox.mkdir();copyroot=sandbox/'resource';copyroot.mkdir()
        for name in descriptor['new_root']['files']:shutil.copyfile(root/name,copyroot/name)
        r.verify_resources(fh,copyroot,descriptor['new_root']['files']);check('own exact three-header root accepted',True)
        extra=copyroot/'stdint.h';extra.write_text('owned shadow');rejects('extra resource header/shadow refused',lambda:r.verify_resources(fh,copyroot,descriptor['new_root']['files']));extra.unlink()
        header=copyroot/'arm_bf16.h';saved=header.read_bytes();header.write_bytes(saved+b'\n');rejects('changed resource bytes refused',lambda:r.verify_resources(fh,copyroot,descriptor['new_root']['files']));header.unlink();rejects('missing resource header refused',lambda:r.verify_resources(fh,copyroot,descriptor['new_root']['files']));header.symlink_to(root/'arm_bf16.h');rejects('resource header symlink refused',lambda:r.verify_resources(fh,copyroot,descriptor['new_root']['files']));header.unlink();header.write_bytes(saved)
        alias=sandbox/'root-alias';alias.symlink_to(copyroot,target_is_directory=True);rejects('resource ancestry symlink refused',lambda:e.canonical_output_path(alias));rejects('bound artifact symlink refused',lambda:e.bound_profile_file({'path':str(alias/'arm_bf16.h'),'sha256':descriptor['new_root']['files']['arm_bf16.h']}))
        fake=copy.deepcopy(rows[0]);fake['cwd']=str(copyroot);fake['bound_source']=str(copyroot/'arm_bf16.h');fake['next_owned_compile_argv_template']=['-I',str(copyroot),'-c',fake['bound_source']];index={str(copyroot/n):h for n,h in descriptor['new_root']['files'].items()}
        e.namespace([fake],index,e.Digests());check('own complete resource namespace accepted',True);extra.write_text('owned new shadow');rejects('complete namespace rejects new shadow',lambda:e.namespace([fake],index,e.Digests()));extra.unlink()
        absent=sandbox/'absent';r.require_absent([absent]);absent.mkdir();rejects('retired absent root materialization refused',lambda:r.require_absent([absent]))
        bad=copy.deepcopy(descriptor);bad['parents']['parent_index']['sha256']='0'*64;rejects('stale parent index refused',lambda:e.resource_profile(profile_args,rows,bad))
        receipt=e.load_project(descriptor['namespace_receipt']['path']);receipt['files'][str(root/'arm_bf16.h')]='0'*64;rp=sandbox/'wrong-receipt.json';e.write(rp,receipt);bad=copy.deepcopy(descriptor);bad['namespace_receipt']={'path':str(rp),'sha256':e.sha(rp)};rejects('changed namespace receipt refused',lambda:e.resource_profile(profile_args,rows,bad))
        index=e.load_project(descriptor['artifact_index']['path']);first=next(iter(e.load_project(parents['parent_index']['path'])['files']));index['files'][first]='0'*64;ip=sandbox/'wrong-index.json';e.write(ip,index);bad=copy.deepcopy(descriptor);bad['artifact_index']={'path':str(ip),'sha256':e.sha(ip)};rejects('inherited index tampering refused',lambda:e.resource_profile(profile_args,rows,bad))
        check('historical resource root remains physically absent',not os.path.lexists(old_root));check('all accepted resource header bytes unchanged',all(e.sha(root/n)==h for n,h in descriptor['new_root']['files'].items()))
        report['after_resources']=supervise.sample();report['outcome']='resource-deferred' if report['after_resources']['MemAvailable_bytes']<4*e.GIB or supervise.pressured(report['after_resources']) else 'pass';report['summary']='Three actual source-only profiles preserve old bytes and BFA8 AST; exact resource1080 transition/keys/index/namespace/authority/resume negatives retained; no compiler'
    except Exception as error:report['error']=repr(error)
    finally:
        report['controller_memory']=e.actual_controller_memory();report['source_hashes']={str(p):e.sha(p) for p in [TOOL,Path(__file__)]};report['artifact_hashes']={str(p):e.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()};report['artifacts']=list(report['artifact_hashes']);report['sha256']=report['artifact_hashes'];e.write(out/'evidence.json',report);print(json.dumps({k:report.get(k) for k in ['outcome','error','controller_memory']}|{'checks':len(checks)},indent=2))
    return report['outcome']!='pass'

if __name__=='__main__':raise SystemExit(main())
