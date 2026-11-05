#!/usr/bin/env python3
"""Read-only KRN039 acceptance bindings and raw native symbols; no execution."""
from datetime import datetime, timezone
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
OWNER = MAIN/'worktrees/krn-039-20261105'
REVIEW = MAIN/'worktrees/rev-kernel-des-20261105'
TIP = 'b1ae6207dea930edab8536b314b844fc25a0cd9e'
REVIEW_TIP = '6b8186c3d586d928cb1bcde4ccf3309a1200a94f'
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while b:=f.read(1048576): h.update(b)
    return h.hexdigest()


def must(test, message):
    if not test: raise ValueError(message)


def load(path): return json.loads(Path(path).read_text())


def rooted(path, base=MAIN):
    return Path(path) if Path(path).is_absolute() else base/path


def symbols(path, wanted):
    """Independent nlist64 walk; skip weak definitions and debug records."""
    definitions={}; imports=set()
    with Path(path).open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
        size=len(data);must(size>=32,'Short native object')
        magic,cpu,subtype,kind,ncmds,cmdbytes,flags,reserved=struct.unpack_from('<IiiIIIII',data)
        must(magic==0xfeedfacf and cpu==0x100000c and kind==1,'Not a real ARM64 Mach-O object')
        must(32+cmdbytes<=size and ncmds<10000,'Invalid commands')
        offset=32; table=None
        for _ in range(ncmds):
            command,length=struct.unpack_from('<II',data,offset)
            must(length>=8 and offset+length<=32+cmdbytes,'Invalid load extent')
            if command==2:
                must(length==24 and table is None,'Ambiguous symbol table')
                table=struct.unpack_from('<IIII',data,offset+8)
            offset+=length
        must(offset==32+cmdbytes and table is not None,'Missing symbol table')
        symoff,count,stroff,strsize=table
        must(symoff+16*count<=size and stroff+strsize<=size,'Invalid nlist extent')
        for index in range(count):
            name_offset,ntype,section,desc,value=struct.unpack_from('<IBBHQ',data,symoff+index*16)
            if ntype&0xe0 or not(ntype&1) or not name_offset: continue
            must(name_offset<strsize,'Invalid string offset')
            end=data.find(b'\0',stroff+name_offset,stroff+strsize)
            must(end>=0,'Unterminated symbol')
            name=data[stroff+name_offset:end].decode('utf-8')
            if ntype&0xe==0 and value==0: imports.add(name)
            if name in wanted and ntype&0xe==0xe and section and not(desc&0x80):
                must(name not in definitions,'Duplicate selected symbol in object')
                definitions[name]=dict(value=value,type=ntype,section=section,desc=desc)
    return definitions,imports


def unpack(path):
    data=Path(path).read_bytes();magic,size=struct.unpack_from('<II',data)
    must(magic==0x50554e58 and size==len(data)-8,'Invalid XNUP framing')
    offset=8;entries={}
    while True:
        name,length,reserved=struct.unpack_from('<16sII',data,offset);offset+=24
        must(reserved==0,'Reserved XNUP field')
        if name==bytes(16):
            must(length==0 and offset==len(data),'Invalid XNUP end')
            return entries
        name=name.rstrip(b'\0').decode();must(name not in entries,'Duplicate XNUP member')
        must(offset+length<=len(data),'XNUP member overflow')
        entries[name]=data[offset:offset+length];offset+=length
        pad=-length%16;must(data[offset:offset+pad]==bytes(pad),'XNUP padding');offset+=pad


def main():
    name=sys.argv[1];must(re.fullmatch(r'[A-Za-z0-9_-]+',name),'Invalid run')
    out=HERE/'runs'/name;out.mkdir(parents=True,exist_ok=False)
    r=dict(kind='source-review',origin='local-host',outcome='fail',task='INT-003',component='KRN-039',
           recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),commands=[],bindings={},admission=[],
           compiler_executed=False,algorithm_replayed=False,guest_executed=False,main_published=False,
           registry_mutated=False,full_kernel_qualified=False,CTS3_native_memory_gate_closed=False)

    def bind(path,expected=None):
        path=Path(path);actual=sha(path)
        must(expected is None or actual==expected,'Changed bound input: '+str(path))
        must(str(path) not in r['bindings'] or r['bindings'][str(path)]==actual,'Conflicting binding')
        r['bindings'][str(path)]=actual
        return actual

    def mapping(data,base=MAIN):
        for path,digest in data.items(): bind(rooted(path,base),digest)

    def git(*args):
        argv=['git','-C',str(MAIN),*args];p=subprocess.run(argv,env=ENV,capture_output=True,timeout=30)
        r['commands'].append(dict(argv=argv,exit_code=p.returncode,stdout_sha256=hashlib.sha256(p.stdout).hexdigest(),stderr_sha256=hashlib.sha256(p.stderr).hexdigest()))
        must(p.returncode==0,'Git source read failed');return p.stdout

    def report(spec):
        path=rooted(spec['path']);bind(path,spec['sha256']);return load(path)

    try:
        bind(__file__);bind(HERE/'README.md')
        for i in range(3):
            n=int(re.search(r'^MemAvailable:\s+(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])
            r['admission'].append(dict(at=datetime.now(timezone.utc).isoformat(),MemAvailable_KiB=n))
            must(n>=4194304,'Source intake deferred below4GiB before children')
            if i<2:time.sleep(1)
        commits=git('rev-list','--reverse','a948c6e^..'+TIP).decode().splitlines()
        must(len(commits)==6,'Unexpected producer series')
        r['source_commits']=commits+[REVIEW_TIP]
        allowed=['docs/procedures/kernel-des/','fixtures/public/xnu-kernel-des/','patches/kernel-des-provider/',
                 'src/platform/crypto/des/kernel_provider.c','src/platform/crypto/des/kernel_provider.h','tools/build/xnu_kernel_des.py']
        for commit in r['source_commits']:
            paths=git('diff-tree','--no-commit-id','--name-only','-r',commit).decode().splitlines()
            scopes=['docs/reviews/krn-039/'] if commit==REVIEW_TIP else allowed
            must(paths and all(any(p==s or p.startswith(s) for s in scopes) for p in paths),'Unscoped commit')
        qualified_path=OWNER/'docs/procedures/kernel-des/qualified-evidence.json'
        bind(qualified_path,'16ebf407f44decbf47af0b7ab12b823d4cf352a33ce6c8db7b86310f727ebf19');q=load(qualified_path)
        receipt_path=REVIEW/'artifacts/rev-kernel-des/20261106-receipt1/evidence.json'
        bind(receipt_path,'1976a7a59882fb03fab705e5a128c096d3b302999166d0f6aacf49b12319ca3b');review=load(receipt_path)
        must(q['outcome']==review['outcome']=='pass' and review['remaining_actionable_P0_P1_P2']==[],'No positive independent receipt')
        raw=report(q['raw_evidence']);must(raw['outcome']=='pass' and len(raw['checks'])==1311 and all(x['passed'] for x in raw['checks']),'Raw1311 binding outcome')
        mapping(review['sha256']);independent=report(review['independent_final']);mapping(independent['sha256'])
        must(independent['outcome']=='pass' and not review['QEMU_executed_by_reviewer'],'Independent review scope')
        reports={}
        for name,spec in q['reports'].items():
            data=report(spec);must(data['outcome']==spec['outcome'],'Historical report relabelled')
            mapping(data['sha256']);reports[name]=data
        mapping(q['owned_source_hashes'],OWNER);mapping(q['metadata_script_hashes'],OWNER)
        mapping(raw['prepared_source_hashes'],OWNER)
        for commit,prefixes,base in [(TIP,allowed,OWNER),(REVIEW_TIP,['docs/reviews/krn-039'],REVIEW)]:
            paths=git('ls-tree','-r','--name-only',commit,*prefixes).decode().splitlines()
            for path in paths:
                data=git('show',commit+':'+path);bind(base/path,hashlib.sha256(data).hexdigest())
        subject=q['source_subject_commit'];must(subject=='8c3797d62efe6a800b9daa48fa01d8008b25b691','Unexpected measured subject')
        late=git('diff','--name-only',subject,TIP).decode().splitlines()
        must(late and all(p.startswith('docs/procedures/kernel-des/') for p in late),'Late production modification')
        manifest=report(q['coherent_component_manifest']);nodes=manifest['objects']
        must(manifest['object_count']==len(nodes)==len({x['id'] for x in nodes})==988,'988-node coherent graph')
        must(manifest['full_provider_startup_executed'] is False,'Native startup promotion')
        targets=set(review['unique_strong_selected_import_providers'])
        must(len(targets)==28,'Selected native import target count')
        providers={s:[] for s in targets};imports={};outputs={}
        for row in nodes:
            for field,digest in [('source','source_sha256'),('output','output_sha256')]:
                bind(rooted(row[field]),row[digest])
            output=rooted(row['output']);must(str(output) not in outputs,'Duplicate object output')
            outputs[str(output)]=row['id'];defs,undef=symbols(output,targets);imports[row['id']]=undef
            for symbol,metadata in defs.items():providers[symbol].append(dict(id=row['id'],output=row['output'],metadata=metadata))
        must(all(len(v)==1 for v in providers.values()),'Selected import lacks unique actual strong provider')
        r['actual_strong_selected_providers']=providers
        new_imports=set().union(*(imports[x] for x in ['component/des-kernel-provider','component/des','component/mbedtls-des']))
        must(new_imports<=targets,'New DES import omitted by selected target set')
        for name,provider in q['strong_clear_and_zeroizer_providers'].items():
            bind(rooted(provider['output']),provider['output_sha256'])
            must(providers[name][0]['id']==provider['id'],'Clearing provider differs from raw bytes')
        must('_memset_s' in imports['osfmk/cc_clear.o'] and '_secure_memset' in imports['osfmk/memset_s.o'],'Real clear call chain missing')
        guest=reports['actual-CPU'];cpu=q['actual_CPU']
        must(guest['outcome']=='pass' and cpu['top_level_CHECKs']==47520 and cpu['vectors']==1964 and cpu['ESP_cases']==120,'Actual CPU workload')
        must(len(guest['guest_cases'])==6 and all(c['accepted'] for c in guest['guest_cases']),'Six actual CPU controls')
        files_by_hash={}
        for path,digest in guest['sha256'].items():files_by_hash.setdefault(digest,[]).append(rooted(path))
        r['runtime_controls']=[]
        for case in guest['guest_cases']:
            bind(rooted(case['image']),case['image_sha256'])
            payload=next(p for p in files_by_hash[case['payload_sha256']] if p.suffix=='.xnup')
            console=next(p for p in files_by_hash[case['console_sha256']] if p.suffix=='.log')
            entries=unpack(payload);must(entries['kernel']==rooted(case['image']).read_bytes(),'Actual payload/image bytes differ')
            text=console.read_text(errors='replace')
            must('DES' in text,'Missing real caller console')
            r['runtime_controls'].append(dict(case=case['case'],result=case['result'],console_sha256=sha(console),
                                             payload_sha256=sha(payload),image_sha256=case['image_sha256']))
        must(cpu['all_owned_children_quiesced'] is True,'CPU survivors')
        # Read actual supervisor records, not only the compact success flags.
        run_records=[]
        for path in guest['sha256']:
            path=rooted(path)
            if path.suffix=='.json':
                data=load(path)
                if 'after' in data and 'argv' in data and 'outcome' in data:
                    after=data['after'];must(after['owned_processes']==[] and after['owned_tree_rss_bytes']==0,'Recorded guest process survived')
                    run_records.append(dict(path=str(path),outcome=data['outcome'],elapsed_seconds=data['elapsed_seconds']))
        must(len(run_records)==6,'Six actual supervisor receipts required')
        for key in ['full_provider_startup_executed','full_kernel_qualified','full_crypto_qualified','private_Apple_ABI_qualified','FIPS_qualified','side_channels_qualified','native_device_qualified','kernel_MMU_qualified']:
            must(q[key] is False,'Unqualified promotion: '+key)
        r['supervisor_records']=run_records;r['native_contract']=q['native_contract'];r['preserved_failed_reports']={k:v for k,v in q['reports'].items() if v['outcome']!='pass'}
        r['outcome']='pass';r['summary']='Frozen039/review receipts, source/object graph and unique selected strong providers verified; six existing payload/control/cleanup records bound; no algorithm or guest replay'
    except Exception as e:r['error']=repr(e);r['summary']='Read-only039 intake failed/deferred; no integration acceptance or mutation'
    finally:
        r['finished_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
        r['process_memory']=[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))]
        (out/'binding-index.json').write_text(json.dumps(r['bindings'],indent=2)+'\n')
        r['artifacts']=[str((out/'binding-index.json').relative_to(MAIN))]
        r['artifact_hashes']={r['artifacts'][0]:sha(out/'binding-index.json')}
        (out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ['outcome','summary','error','process_memory']},indent=2))
    return r['outcome']!='pass'


if __name__=='__main__':raise SystemExit(main())
