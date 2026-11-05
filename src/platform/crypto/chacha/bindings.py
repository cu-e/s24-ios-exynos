#!/usr/bin/env python3
"""Requalify changed typed binding/guest only; reuse exact proven crypto objects."""
import argparse,datetime,json,re,shutil,subprocess,sys
from pathlib import Path
import check,addresses
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--from-run',required=True);ap.add_argument('--run',required=True);ap.add_argument('--experiment',default='CHACHA-005');args=ap.parse_args()
    for name in [args.run,args.from_run]:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',name):raise ValueError('Simple fresh run names required')
    root,main,here=check.ROOT,check.MAIN,check.HERE;oldout=root/'artifacts/crypto-chacha'/args.from_run;out=root/'artifacts/crypto-chacha'/args.run;out.mkdir(parents=True,exist_ok=False)
    r=dict(task='KRN-034',kind='host-test',origin='local-host',outcome='inconclusive',supported_host_arm='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],complete_table_qualified=False,incnonce_supported=False,guest_executed=False,native_device=False,provider_registered=False,xnu_executed=False)
    def command(argv,name):
        r['plan_before_last_child']=check.plan(args.experiment)
        mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        if mem<4*1024**3:raise ValueError('Memory guard: below4GiB; no child started')
        q=check.accepted.run(argv,out,name,30,256);q['MemAvailable_before_bytes']=mem;r['commands'].append(q)
        if q['exit_code']!=0 or q['outcome']!='pass':raise ValueError(name+' failed')
    try:
        r['plan']=check.plan(args.experiment);oldpath=oldout/'evidence.json';old=json.loads(oldpath.read_text())
        if old.get('supported_host_arm')!='pass':raise ValueError('Passing supported original host/ARM capsule required')
        r['reused_host_crypto_evidence']={'path':str(oldpath.relative_to(main)),'sha256':check.sha(oldpath),'host_vectors':old['host_vectors'],'host_checks':old['host_checks'],'reason':'Crypto core, primitives,profile,independent corpus and shared suite remain byte-identical; only bindings/guest changed'}
        r['source_inputs']=check.sources();r['source_changes']={}
        allowed={'src/platform/crypto/chacha/'+n for n in ['functions.c','functions.h','guest.c','check.py','cpu.py']}
        for name,wanted in old['source_inputs'].items():
            actual=check.sha(root/name)
            if actual!=wanted:
                if name not in allowed:raise ValueError('Proven crypto/suite input changed '+name)
                r['source_changes'][name]={'before':wanted,'after':actual}
        for name,wanted in old['sha256'].items():
            if check.sha(main/name)!=wanted:raise ValueError('Original capsule changed '+name)
        r['commit']=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip();r['commit_role']='Base; actual changed binding/guest source snapshot retained'
        for name in r['source_inputs']:
            dest=out/'source-snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,dest)
        for key in ['tools','imported_objects','accepted_xts_evidence','target_layout','host_vectors','host_checks','vectors','sanitizer_controls','profile_rejections','selected_source_checks']:
            r[key]=old[key]
        for name,wanted in r['imported_objects'].items():
            if check.sha(name)!=wanted:raise ValueError('Accepted object changed '+name)
        r['reused_objects']={}
        for name in ['adapter','chacha','poly','suite']:
            p=oldout/('arm-'+name+'.o');shutil.copyfile(p,out/p.name);r['reused_objects'][str(p.relative_to(main))]=check.sha(p)
        shutil.copytree(oldout/'regenerated',out/'regenerated')
        recipe=next(q['argv'] for q in old['commands'] if str(here/'functions.c') in q['argv'] and '-c' in q['argv']);flags=recipe[1:recipe.index('-MMD')];arm=Path(recipe[0]);ld=Path(r['tools']['linker']['path'])
        if check.sha(arm)!=r['tools']['arm']['sha256'] or check.sha(ld)!=r['tools']['linker']['sha256']:raise ValueError('Compiler/linker changed')
        for name,p in [('functions',here/'functions.c'),('cpu-functions',here/'functions.c'),('guest',here/'guest.c'),('spin',here/'guest.c')]:
            extra=['-DCHACHA_CPU_FIXTURE'] if name!='functions' else []
            if name=='spin':extra+=['-DCHACHA_SPIN']
            command([arm,*flags,*extra,'-MMD','-MF',out/('arm-'+name+'.d'),'-c',p,'-o',out/('arm-'+name+'.o')],'arm-'+name)
        command([arm,*flags,'-DCHACHA_CPU_FIXTURE','-S',here/'functions.c','-o',out/'runtime-functions.s'],'runtime-functions-assembly')
        body=(out/'runtime-functions.s').read_text().split('_s24_chacha20poly1305_fill:',1)[1].split('; -- End function',1)[0]
        r['runtime_callback_address_proof']={}
        methods=['info','init','reset','setnonce','incnonce','aad','encrypt','finalize','decrypt','verify']
        for name in methods:
            symbol='_s24_chacha_'+name;good=any(symbol+'@'+form in body and symbol+'@'+form+'OFF' in body for form in ['PAGE','GOTPAGE'])
            r['runtime_callback_address_proof'][symbol]=good
            if not good:raise ValueError('Runtime address does not reference genuine callback '+symbol)
        stores=len(re.findall(r'^\s*str\s+x\d+,',body,re.M));r['volatile_pointer_store_instructions']=stores
        if stores!=10 or re.search(r'\bbl\s+_?(memcpy|memmove)\b',body):raise ValueError('Runtime binding folded to constant pointer pool')
        sys.path.insert(0,str(main/'tools/build'));from xnu_kernel_syscalls import ObjectData
        obj=ObjectData(out/'arm-functions.o');r['table_layout']=obj.value('_s24_chacha_table_layout','<2Q');r['typed_method_relocations']=[]
        for i,name in enumerate(methods):
            row=obj.relocation('_functions',i*8)
            if row['name']!='_s24_chacha_'+name or row['addend']!=0:raise ValueError('Native constant binding mismatch')
            r['typed_method_relocations'].append(row)
        if tuple(r['table_layout'])!=(80,8):raise ValueError('Genuine table layout changed')
        dep=Path(r['accepted_xts_evidence']['path']).parent
        for mode,last in [('normal','guest'),('spin','spin')]:
            command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('arm-'+n+'.o') for n in ['adapter','chacha','poly','suite','cpu-functions',last]],dep/'arm-adapter.o',dep/'arm-aes.o',dep/'arm-memory.o','-o',out/(mode+'.macho')],mode+'-link')
        r['images']={mode:check.accepted.avf.macho(out/(mode+'.macho')) for mode in ['normal','spin']}
        nm=Path(r['tools']['nm']['path']);command([nm,'--defined-only',out/'normal.macho'],'arm-defined-symbols')
        definitions=(out/'arm-defined-symbols.log').read_text().splitlines()
        if sum(line.split()[-1]=='_mbedtls_platform_zeroize' for line in definitions if line.split())!=1:raise ValueError('Single imported zeroizer required')
        r['linked_runtime_address_proof']=addresses.prove(out/'normal.macho','\n'.join(definitions),r['images']['normal'])
        # Real negative changes the first actual STR field offset in OWN image.
        damaged=bytearray((out/'normal.macho').read_bytes());at=r['linked_runtime_address_proof']['initializers']['_s24_chacha_cpu_prepare'][0]['instruction_file_offset'];damaged[at+1]^=4
        negative=out/'bad-table-field.macho';negative.write_bytes(damaged)
        try:addresses.prove(negative,'\n'.join(definitions),r['images']['normal'])
        except ValueError as error:r['linked_address_negative']={'detected':True,'mutation_file_offset':at,'error':str(error)}
        else:raise ValueError('Changed real callback field escaped address proof')
        r['dependency_hashes']={}
        for p in out.glob('*.d'):
            for name in p.read_text().replace('\\\n',' ').split(':',1)[1].split():r['dependency_hashes'][str(Path(name).resolve())]=check.sha(name)
        r['supported_host_arm']='pass';r['summary']='Changed genuine typed native/runtime bindings and fixture compiled;10actualPC-relative callback stores verified; unchanged59vector123999host crypto proof reused; CPU execution pending separatelease'
    except Exception as error:r['error']=repr(error)
    finally:
        r['artifacts']=[str(p.relative_to(main)) for p in out.rglob('*') if p.is_file()];r['sha256']={str(p.relative_to(main)):check.sha(p) for p in out.rglob('*') if p.is_file()};r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ['outcome','supported_host_arm','host_vectors','host_checks','volatile_pointer_store_instructions','error']}));return r['supported_host_arm']!='pass'
if __name__=='__main__':raise SystemExit(main())
