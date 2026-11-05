#!/usr/bin/env python3
"""Independent bounded bytes/transition review; never invokes the producer run."""
import argparse
import copy
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR = MAIN / 'worktrees/vm-038-20261106'
FROZEN = '2e9956ce4d02dd13932513f3049ab2e22b4ee90d'
RUN = AUTHOR / 'docs/procedures/avf-firehose-namespace/qualification-session1'
REC = {'kind':'source-review','origin':'local-host','task':'INT-003','experiment':'PLATFHNS-001',
       'recorded_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
       'source_commit':FROZEN,'checks':[],'commands':[],'bindings':{},'controls':[],
       'compiler_executed':False,'preprocessor_or_generator_executed':False,
       'parent_physical_file_matrix_rehashed':False,'historical_inputs_mutated':False}


def canon(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def sha(p):
    p=Path(p)
    with p.open('rb') as stream: h=hashlib.file_digest(stream,'sha256').hexdigest()
    REC['bindings'][str(p)]=h
    return h


def require(name,value):
    REC['checks'].append({'name':name,'pass':bool(value)})
    if not value: raise ValueError(name)


def load(p,expected=None):
    digest=sha(p)
    if expected: require('pinned '+str(p),digest==expected)
    with Path(p).open() as stream: return json.load(stream)


def command(cwd,argv):
    p=subprocess.run(argv,cwd=cwd,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0'),
                     capture_output=True,timeout=30)
    REC['commands'].append({'argv':argv,'cwd':str(cwd),'exit_code':p.returncode,
                            'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr':p.stderr.decode()})
    require('read-only command '+argv[0],p.returncode==0)
    return p.stdout


def reject(name,action):
    try: action()
    except (ValueError,OSError,KeyError) as error:
        REC['controls'].append({'name':name,'rejected':True,'diagnostic':str(error)})
    else: raise ValueError('Actual production helper admitted '+name)


def review(out):
    sha(__file__)
    code_path=AUTHOR/'tools/build/avf_firehose_namespace.py'
    code=code_path.read_bytes(); sha(code_path)
    committed=(out/'qualifier-source.py').read_bytes();sha(out/'qualifier-source.py')
    require('actual module equals committed source bytes',code==committed)
    module=types.ModuleType('frozen_qualifier'); module.__file__=str(code_path)
    exec(compile(code,str(code_path),'exec'),module.__dict__)
    fixture=AUTHOR/'fixtures/public/avf-firehose-namespace/inputs.json'
    require('actual fixture equals committed captured bytes',fixture.read_bytes()==(out/'fixture-source.json').read_bytes())
    pins=load(fixture)
    wrapper=load(AUTHOR/'docs/procedures/avf-firehose-namespace/evidence.json',
                 '45df6cf7d39823be544bce12d386c088c9bb814bf2afd6d0a6e082802fdff633')
    require('original actual source qualification scope',wrapper['outcome']=='pass' and
            not wrapper['compiler_executed'] and not wrapper['old_namespaces_modified'])
    descriptor=load(RUN/'qualified-component.json',
                    '3343a382452d05c382a15ea54e3835c3125c67c451cb586a1c3ed5a939b37174')
    for name,value in descriptor.items():
        if isinstance(value,dict) and set(['path','sha256'])<=value.keys(): load_or_hash=sha(value['path']);require('descriptor binding '+name,load_or_hash==value['sha256'])
    for name,binding in descriptor['parents'].items():
        require('exact declared parent '+name,binding['path']==str(MAIN/pins[name]) and
                binding['sha256']==pins[name+'_sha256'] and sha(binding['path'])==binding['sha256'])
    old=load(MAIN/pins['parent_manifest'],pins['parent_manifest_sha256'])
    new=load(descriptor['object_manifest']['path'],descriptor['object_manifest']['sha256'])
    old_root=Path(descriptor['old_root']['path']); root=Path(descriptor['new_root']['path'])
    require('canonical old root and continued absence',old_root==MAIN/module.OLD_ROOT and not os.path.lexists(old_root))
    require('ordered exact 1080 IDs',len(old)==len(new)==1080 and [x['id']for x in old]==[x['id']for x in new])
    edit_counts=[]
    for before,after in zip(old,new):
        require('all non-template fields '+before['id'],
                {k:v for k,v in before.items()if k!='next_owned_compile_argv_template'}==
                {k:v for k,v in after.items()if k!='next_owned_compile_argv_template'})
        a=before['next_owned_compile_argv_template']; b=after['next_owned_compile_argv_template']
        require('same token count '+before['id'],len(a)==len(b))
        changes=[i for i,(x,y)in enumerate(zip(a,b))if x!=y]
        require('one genuine declared include token '+before['id'],len(changes)==1 and
                ((a[changes[0]],b[changes[0]])==('-I'+str(old_root),'-I'+str(root)) or
                 (a[changes[0]],b[changes[0]])==(str(old_root),str(root)) and changes[0]>0 and a[changes[0]-1]=='-I'))
        edit_counts.append(changes[0])
    require('55 generated entries preserved',sum(x['generated_input'] for x in new)==55)
    require('real helper accepts frozen whole transition',len(module.validate_transition(old,new,old_root,root))==1080)
    target=next(i for i,x in enumerate(new)if x['id']=='libkern/log.o')
    for name,change in [('later override',lambda x:x['next_owned_compile_argv_template'].append('-UDEVELOPMENT')),
                        ('wrong source',lambda x:x.update(bound_source_sha256='0'*64)),
                        ('wrong compiler',lambda x:x['next_owned_compile_argv_template'].__setitem__(0,'/owned/wrong-clang')),
                        ('wrong generated membership',lambda x:x.update(generated_input=not x['generated_input']))]:
        altered=list(new);altered[target]=dict(new[target]);altered[target]['next_owned_compile_argv_template']=list(new[target]['next_owned_compile_argv_template']);change(altered[target])
        reject(name,lambda:module.validate_transition(old,altered,old_root,root))
    swapped=list(new);swapped[0],swapped[1]=swapped[1],swapped[0]
    reject('reordered IDs',lambda:module.validate_transition(old,swapped,old_root,root))
    header=root/module.HEADER
    require('exact real licensed one-header install',module.overlay_files(root)=={module.HEADER:pins['exported_header_sha256']} and sha(header)==pins['exported_header_sha256'])
    for name,setup in [('missing',lambda p:None),('shadow',lambda p:(shutil.copyfile(header,p/module.HEADER),(p/'stdint.h').write_text('extra'))),
                       ('changed',lambda p:(p/module.HEADER).write_bytes(header.read_bytes()+b'\n')),
                       ('symlink',lambda p:(p/module.HEADER).symlink_to(header))]:
        p=out/('overlay-'+name);(p/'os').mkdir(parents=True);setup(p)
        reject('actual filesystem overlay '+name,lambda:module.verify_overlay(p,pins['exported_header_sha256']))
    parent_ns=load(MAIN/pins['parent_namespace_receipt'],pins['parent_namespace_receipt_sha256'])
    ns=load(descriptor['namespace_receipt']['path'],descriptor['namespace_receipt']['sha256'])
    require('accepted old namespace digest',canon({k:parent_ns[k]for k in ['roots','absent_search_roots','files']})==pins['parent_namespace_digest'])
    expected={'roots':sorted([*parent_ns['roots'],str(root)],key=lambda x:(len(Path(x).parts),x)),
              'absent_search_roots':[x for x in parent_ns['absent_search_roots']if x!=str(old_root)],
              'files':{**parent_ns['files'],str(header):pins['exported_header_sha256']}}
    expected['sha256']=canon(expected)
    require('exact 6721 plus one namespace',ns==expected and len(ns['files'])==6722 and
            descriptor['namespace_digest']==expected['sha256'])
    require('all historical optional roots remain absent',not any(os.path.lexists(x) for x in parent_ns['absent_search_roots']))
    keys=load(descriptor['object_input_keys']['path'],descriptor['object_input_keys']['sha256'])['keys']
    require('1080 keys',len(keys)==1080)
    for row,item in zip(new,keys):
        binding={'schema':module.SCHEMA,'id':row['id'],'manifest_sha256':descriptor['object_manifest']['sha256'],
                 'namespace_sha256':expected['sha256'],'source':row['bound_source'],'source_sha256':row['bound_source_sha256'],
                 'configuration':row['configuration'],'configuration_sha256':row['configuration_sha256'],
                 'compiler':row['next_owned_compile_argv_template'][0],'cwd':row['cwd'],
                 'argv_template_sha256':canon(row['next_owned_compile_argv_template'])}
        require('complete key binding '+row['id'],item=={'id':row['id'],'input_key':canon(binding),'binding':binding})
    selectors=load(descriptor['selectors']['path']);old_sel=load(MAIN/pins['parent_selectors'],pins['parent_selectors_sha256'])
    require('all selector fields except manifest identity unchanged',
            {k:v for k,v in selectors.items()if k not in ['source_manifest','sha256']}==
            {k:v for k,v in old_sel.items()if k not in ['source_manifest','sha256']} and
            selectors['sha256']==descriptor['object_manifest']['sha256'] and
            (MAIN/selectors['source_manifest']).resolve()==Path(descriptor['object_manifest']['path']))
    del old,new,keys,swapped,altered;gc.collect()
    inherited=load(MAIN/pins['parent_index'],pins['parent_index_sha256'])['files']
    indexed=load(descriptor['artifact_index']['path'],descriptor['artifact_index']['sha256'])['files']
    require('all 53976 inherited index entries equal',len(inherited)==53976 and all(indexed.get(k)==v for k,v in inherited.items()))
    extra={k:v for k,v in indexed.items()if k not in inherited}
    require('21 newly published actual inputs',len(extra)==21 and all(sha(Path(k))==v for k,v in extra.items()))
    normalized={}
    for name,digest in indexed.items():
        if '..' in Path(name).parts: raise ValueError('Nonliteral index path '+name)
        p=str((MAIN/Path(name)).absolute())
        if p in normalized and normalized[p]!=digest: raise ValueError('Conflicting normalized alias '+name)
        normalized[p]=digest
    require('all index paths literal and normalized aliases consistent',True)
    require('entire new namespace covered by complete index',all(normalized.get(k)==v for k,v in ns['files'].items()))
    REC['inherited_entries_compared_not_physically_rehashed']=len(inherited)
    REC['new_publication_inputs_hashed']=len(extra)
    del indexed,inherited,normalized;gc.collect()
    source=MAIN/'references/xnu-kernel-firehose'
    tree=(out/'source-blobs.txt').read_text();sha(out/'source-blobs.txt')
    blobs={x.split('\t')[1]:x.split()[2]for x in tree.splitlines()}
    for name,digest in pins['source_files_sha256'].items():
        p=source/name;body=p.read_bytes()
        require('canonical full Git blob '+name,sha(p)==digest and
                hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()==blobs[name])
    module.verify_export_recipe((source/'xcodeconfig/libfirehose_kernel.xcconfig').read_text(),
                               (source/'libdispatch.xcodeproj/project.pbxproj').read_text(),module.FLAGS)
    reject('changed real kernel export flags',lambda:module.verify_export_recipe(
        (source/'xcodeconfig/libfirehose_kernel.xcconfig').read_text(),
        (source/'libdispatch.xcodeproj/project.pbxproj').read_text(),module.FLAGS+['-UKERNEL']))
    # Real production output guard, with only its root constant redirected to an owned synthetic project.
    fake=out/'controlled-project';fake.mkdir();saved_root=module.ROOT;module.ROOT=fake
    allowed=fake/'docs/procedures/avf-firehose-namespace';allowed.mkdir(parents=True)
    for name,p in [('outside',out/'outside'),('traversal',allowed/'..'/'escape')]:
        reject('output '+name,lambda:module.run(argparse.Namespace(main=MAIN,output=p)))
        require('output '+name+' creates nothing',not p.exists())
    destination=out/'symlink-destination';destination.mkdir();(allowed/'link').symlink_to(destination,target_is_directory=True)
    reject('output parent symlink',lambda:module.run(argparse.Namespace(main=MAIN,output=allowed/'link'/'new')))
    require('symlink target untouched',list(destination.iterdir())==[])
    exists=allowed/'existing';exists.mkdir()
    reject('existing output overwrite',lambda:module.run(argparse.Namespace(main=MAIN,output=exists)))
    require('existing output untouched',list(exists.iterdir())==[]);module.ROOT=saved_root
    require('historical root remains absent after controls',not os.path.lexists(old_root))
    REC.update(outcome='pass',summary='Bounded independent actual code/metadata/Git-body and real-FS transition review passed; no compiled dependency/ABI/consumer or boot qualification.')


args=argparse.ArgumentParser();args.add_argument('--out',type=Path,required=True);args=args.parse_args()
status=0
try: review(args.out)
except Exception as error: REC.update(outcome='fail',error=repr(error));status=1
finally:
    REC['finished_at']=datetime.now(timezone.utc).isoformat();REC['exit_code']=status
    REC['process_memory']=[x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith(('VmRSS:','VmHWM:'))]
    (args.out/'evidence.json').write_text(json.dumps(REC,indent=2)+'\n')
    print(json.dumps({'outcome':REC['outcome'],'checks':len(REC['checks']),'controls':len(REC['controls']),'error':REC.get('error')}))
sys.exit(status)
