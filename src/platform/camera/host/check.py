#!/usr/bin/env python3
"""Bounded CAM-003 source/oracle/host checks; no camera or device operations."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
from oracle import generate
from source import FILES,PREFIX,REVISION

ROOT=Path(__file__).resolve().parents[4]
SRC=Path(__file__).resolve().parent
LAB=Path('/home/egor/dev/pet/s24-ios-exynos')
HOST=Path('/home/egor/.local/bin/clang')
TARGET=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True)
    parser.add_argument('--source-cache',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',args.run):raise ValueError('Canonical fresh run required')
    out=ROOT/'artifacts/camera-host'/args.run
    if out.resolve()!=out:raise ValueError('Symlink output forbidden')
    out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),commands=[],checks=[],
        summary='Source-qualified camera frame-plane host admission;actual outputs retained',
        device_io=False,ISP_executed=False,DMA_mapping=False,ARM_executed=False,Apple_camera_ABI=False,native_CAM001_completed=False)
    def check(name,value,**data):report['checks'].append(dict(name=name,pass_check=bool(value),**data))
    def run(argv,label,env=None,timed=False,success=True):
        argv=[str(a) for a in argv]
        if timed:argv=['/usr/bin/time','-v',*argv]
        r=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True,timeout=45,env=env)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        report['commands'].append(dict(argv=argv,cwd=str(ROOT),exit_code=r.returncode,stdout=str((out/(label+'.stdout')).relative_to(LAB)),stderr=str((out/(label+'.stderr')).relative_to(LAB))))
        if timed:
            match=re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',r.stderr)
            check(label+'-RSS-budget',match and int(match[1])<=256*1024,maximum_RSS_kib=int(match[1]) if match else None)
        if success and r.returncode:raise RuntimeError(label+' failed: '+r.stderr[-1500:])
        return r
    try:
        snap=out/'implementation';snap.mkdir()
        for path in SRC.iterdir():
            if path.is_file():shutil.copyfile(path,snap/path.name)
        cache=out/'source';cache.mkdir()
        records=json.loads((args.source_cache/'provenance.json').read_text())
        tree=run(['git','-C',LAB/'references/s24-linux','ls-tree','-r',REVISION,'--',*FILES],'exact-pin-Git-tree',env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}).stdout
        blobs={line.split('\t',1)[1]:line.split('\t',1)[0].split()[2] for line in tree.splitlines()}
        for name in FILES:
            original=args.source_cache/name;target=cache/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
            row=next(r for r in records if r['source']==name)
            check('pinned-source-'+name,row['revision']==REVISION and row['sha256']==sha(target))
            data=target.read_bytes()
            blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            check('actual-Git-blob-'+name,blob==blobs.get(name),expected_blob=blobs.get(name),actual_blob=blob)
            modified=data+b'changed-for-provenance-negative-control'
            changed_blob=hashlib.sha1(b'blob '+str(len(modified)).encode()+b'\0'+modified).hexdigest()
            check('reject-altered-source-'+name,changed_blob!=blobs.get(name))
        (cache/'provenance.json').write_text(json.dumps(records,indent=2)+'\n')
        config=(cache/'arch/arm64/configs/e1s_defconfig').read_text();makefile=(cache/PREFIX/'Makefile').read_text()
        check('E1S-selected-v12.1-uses-v12.0-headers','CONFIG_PABLO_V12_1_0=y' in config and 'subdir-ccflags-$(CONFIG_PABLO_V12_1_0) += -I$(srctree)/drivers/media/platform/exynos/camera/include/v12_0_0' in makefile)
        profile=json.loads((snap/'profile.json').read_text())
        check('native-gates-remain-unqualified',all(value is False for value in profile['native_gates'].values()) and profile['crop']['MCSC_programming_qualified'] is False)
        csis=(cache/PREFIX/'is-device-csi_v4.c').read_text();mcsp=(cache/PREFIX/'ischain/is-v12_0_0/is-subdev-mcsp.c').read_text()
        check('CSIS-separates-frame-DMA-and-error-events',all(token in csis for token in ['csi_frame_start_inline','csi_frame_end_inline','CSIS_NOTIFY_DMA_END','VB2_BUF_STATE_ERROR']))
        check('MCSC-additional-crop-stride-policy-remains-explicit',all(token in mcsp for token in ['MCSC_OFFSET_ALIGN','MCSC_WIDTH_ALIGN','MCSC_HEIGHT_ALIGN','ALIGN(mcs_output->dma_stride_y, 16)']))
        oracle=out/'oracle';report['extracted_formats']=generate(cache,oracle)
        run([HOST,'--version'],'host-compiler')
        run([HOST,'-print-resource-dir'],'host-sanitizer-resource')
        control=out/'control.c';control.write_text('#include <limits.h>\n#include <stdlib.h>\nint main(int argc,char **argv){if(argc>1 && argv[1][0]==\'a\'){volatile int i=8;volatile char *p=malloc(4);if(!p)return 2;p[i]=1;free((void*)p);}else{volatile int a=INT_MAX,b=1;volatile int c=a+b;(void)c;}return 0;}\n')
        sanitizer=['-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
        strict=['-Wall','-Wextra','-Werror']
        run([HOST,'-std=c11',*strict,*sanitizer,control,'-o',out/'control'],'control-build',timed=True)
        environment={**os.environ,'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'}
        for name,diagnostic in [('asan','AddressSanitizer: heap-buffer-overflow'),('ubsan','runtime error: signed integer overflow')]:
            r=run([out/'control',name],'negative-'+name,env=environment,success=False)
            check('negative-'+name+'-runtime-detects-fault',r.returncode!=0 and diagnostic in r.stderr)
        run([HOST,'-std=c11',*strict,*sanitizer,'-I',oracle,'-I',snap,snap/'frame.c',snap/'fixture.c',oracle/'donor.c','-o',out/'fixture'],'sanitizer-build',timed=True)
        r=run([out/'fixture'],'sanitizer-fixture',env=environment)
        report['result']=json.loads(r.stdout)
        check('genuine-donor-calculation-comparisons',report['result']['outcome']=='pass' and report['result']['real_donor_vectors']==5120 and report['result']['mutations']==20000)
        expected=struct.pack('<9Q',*report['result']['donor_layout']).hex()
        run(['cc','-std=c11',*strict,'-Wpedantic','-c',snap/'frame.c','-o',out/'host-frame.o'],'host-c',timed=True)
        run(['c++','-std=c++17',*strict,'-Wpedantic','-c',snap/'layout.cpp','-o',out/'host-layout.o'],'host-cpp',timed=True)
        run([TARGET,'--version'],'target-compiler')
        for target,label,section in [('aarch64-none-elf','aarch64-elf','.cam_layout'),('arm64-apple-ios16.5','arm64-ios','__camlayout')]:
            for name,source,standard in [('frame',snap/'frame.c','c11'),('layout',snap/'layout.cpp','c++17'),('donor',oracle/'donor.c','c11')]:
                obj=out/(label+'-'+name+'.o')
                run([TARGET,'--target='+target,'-ffreestanding','-std='+standard,*strict,'-I',oracle,'-c',source,'-o',obj],label+'-'+name+'-build',timed=True)
                headers=run([TARGET.parent/'llvm-readobj','--file-headers',obj],label+'-'+name+'-headers').stdout
                check(label+'-'+name+'-actual-object-format',('elf64-littleaarch64' if label=='aarch64-elf' else 'Mach-O arm64') in headers)
                if name=='frame':
                    imports=run([TARGET.parent/'llvm-nm','--undefined-only',obj],label+'-frame-imports').stdout
                    symbols=[line.split()[-1] for line in imports.splitlines() if line.strip()]
                    normalized=[symbol[1:] if label=='arm64-ios' and symbol.startswith('_') else symbol for symbol in symbols]
                    check(label+'-only-declared-kernel-runtime-imports',set(normalized)<= {'memcpy','memset','__stack_chk_fail','__stack_chk_guard'},actual_symbols=symbols,required_native_runtime='Verified memory and stack-guard providers remain native integration requirements;object compilation is not a native link',native_provider_resolution_qualified=False)
                    if label=='arm64-ios':
                        graph=LAB/'artifacts/xnu-kernel-symbol-gaps/production-session1'
                        report['readonly_provider_graph']={}
                        for graph_name in ['compiled-objects.json','symbol-providers.json']:
                            original=graph/graph_name;shutil.copyfile(original,out/graph_name)
                            report['readonly_provider_graph'][str(original.relative_to(LAB))]=sha(original)
                        providers=json.loads((graph/'symbol-providers.json').read_text())
                        objects={row['id']:row for row in json.loads((graph/'compiled-objects.json').read_text())}
                        report['available_provider_objects']=[];defined={}
                        for symbol in symbols:
                            candidates=providers.get(symbol,[]);available=[]
                            for candidate in candidates:
                                row=objects.get(candidate['object'])
                                if not row:continue
                                provider=LAB/row['output'];source=LAB/row['source']
                                hashes_match=provider.is_file() and source.is_file() and sha(provider)==row['output_sha256'] and sha(source)==row['source_sha256']
                                if hashes_match and row['id'] not in defined:
                                    nm=run([TARGET.parent/'llvm-nm','--defined-only',provider],'provider-'+row['id'].replace('/','-')).stdout
                                    defined[row['id']]=set(line.split()[-1] for line in nm.splitlines() if line.strip())
                                if hashes_match and symbol in defined.get(row['id'],set()):
                                    available.append(row)
                            report['available_provider_objects'].append(dict(symbol=symbol,providers=available,native_link_or_execution_qualified=False))
                            check('actual-current-graph-provider-'+symbol,bool(available),actual_available_objects=[row['id'] for row in available])
                if name=='donor':
                    dump=run([TARGET.parent/'llvm-objdump','--section='+section,'--full-contents',obj],label+'-donor-layout').stdout
                    parts=[]
                    for line in dump.splitlines():
                        match=re.match(r'\s*[\da-fA-F]+\s+((?:[\da-fA-F]{8}\s*){1,4})',line)
                        if match:parts.append(''.join(match[1].split()))
                    actual=''.join(parts)
                    check(label+'-exact-pinned-metadata-layout',actual==expected,expected_hex=expected,actual_hex=actual)
        report['outcome']='pass' if all(row['pass_check'] for row in report['checks']) else 'fail'
    except Exception as error:report['error']=repr(error)
    paths=sorted(path for path in out.rglob('*') if path.is_file())
    report['artifacts']=[str(path.relative_to(LAB)) for path in paths]
    report['sha256']={str(path.relative_to(LAB)):sha(path) for path in paths}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    report['artifacts'].append(str((out/'report.json').relative_to(LAB)));report['sha256'][str((out/'report.json').relative_to(LAB))]=sha(out/'report.json')
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','error','result']},indent=2))
    return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
