#!/usr/bin/env python3
"""Qualify bounded host PCM code against pinned real declarations/calculations."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

import oracle
import source

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("owned_supervisor", ROOT / "tools/build/qemu_host.py")
supervisor = importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
GUARDS = source.GUARDS
ENV = dict(os.environ) | GUARDS | {"ASAN_OPTIONS": "detect_leaks=0:abort_on_error=1",
                                "UBSAN_OPTIONS": "halt_on_error=1:print_stacktrace=1"}


def sha(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def run(argv, out, name, timeout=20):
    record={"argv":[str(a) for a in argv],"started_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "timeout_seconds":timeout,"environment_overrides":{k:ENV[k] for k in [*GUARDS,"ASAN_OPTIONS","UBSAN_OPTIONS"]}}
    start=time.monotonic();peak=0
    def limit():resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with (out/(name+".log")).open("xb") as log,(out/(name+".samples.jsonl")).open("x") as samples:
        p=subprocess.Popen(record["argv"],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                           start_new_session=True,env=ENV,preexec_fn=limit)
        record["owned_session"]=p.pid
        try:
            while p.poll() is None:
                s=supervisor.sample(p.pid);own=int(Path('/proc/self/statm').read_text().split()[1])*resource.getpagesize()
                s["total_owned_rss_bytes"]=own+s["owned_tree_rss_bytes"];peak=max(peak,s["total_owned_rss_bytes"])
                samples.write(json.dumps(s)+"\n");samples.flush()
                if peak>256*1024**2 or time.monotonic()-start>timeout:
                    record["terminated"]= "rss-budget" if peak>256*1024**2 else "deadline"
                    supervisor.terminate(p);break
                time.sleep(0.025)
            record["exit_code"]=p.wait(timeout=2)
        finally:
            if any(x["state"]!="Z" for x in supervisor.sample(p.pid)["owned_processes"]):supervisor.terminate(p)
            until=time.monotonic()+2;s=supervisor.sample(p.pid)
            while any(x["state"]!="Z" for x in s["owned_processes"]) and time.monotonic()<until:
                time.sleep(0.02);s=supervisor.sample(p.pid)
            record.update(elapsed_seconds=round(time.monotonic()-start,3),peak_total_owned_rss_bytes=peak,after=s)
            (out/(name+".json")).write_text(json.dumps(record,indent=2)+"\n")
            if any(x["state"]!="Z" for x in s["owned_processes"]):raise RuntimeError("Owned child survived cleanup")
    return record


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--cc',default='/usr/bin/cc')
    p.add_argument('--clang',default='/home/egor/.local/bin/clang')
    p.add_argument('--host-clang',default='/home/egor/.local/bin/clang');args=p.parse_args()
    cache=args.cache.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    records=[];report={"kind":"host-test","origin":"local-host","outcome":"fail","recorded_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "source_commit":source.COMMIT,"device_executed":False,"native_audio_qualified":False,"commands":records,
                      "argv":[sys.executable,*sys.argv]}
    def must(argv,name):
        r=run(argv,out,name);records.append(r)
        if r['exit_code'] or r.get('terminated'):raise RuntimeError(name+' failed; see retained log')
        return r
    try:
        revision_argv=['git','-C',str(ROOT),'rev-parse','HEAD']
        revision=subprocess.run(revision_argv,capture_output=True,text=True,env=ENV,timeout=10,check=True)
        report['commit']=revision.stdout.strip()
        records.append({'argv':revision_argv,'exit_code':revision.returncode,'environment_overrides':GUARDS})
        verified=json.loads((cache/'verified-sources.json').read_text())
        profile=json.loads((HERE/'profile.json').read_text())
        if verified['commit']!=source.COMMIT or profile['commit']!=source.COMMIT:raise ValueError('Wrong selected source commit')
        if {item['path'] for item in verified['files']}!=set(profile['source_files']):raise ValueError('Incomplete fixed source profile')
        for item in verified['files']:
            path=cache/item['path']
            pinned=profile['source_files'][item['path']]
            if path.stat().st_size!=pinned['size']:raise ValueError('Changed task-cache source extent '+item['path'])
            data=path.read_bytes()
            if item['sha256']!=pinned['sha256'] or item['blob_id']!=pinned['blob_id'] or sha(path)!=pinned['sha256'] or hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=pinned['blob_id']:
                raise ValueError('Changed task-cache source '+item['path'])
        report['fixed_profile_sha256']=sha(HERE/'profile.json')
        report['owned_source_sha256']={str(p.relative_to(ROOT)):sha(p) for p in HERE.iterdir() if p.suffix in ['.c','.h','.py','.json']}
        report['source_manifest_sha256']=sha(cache/'verified-sources.json')
        report['source_oracle']=oracle.generate(cache,out)
        report['tools']={}
        for name,tool in [('cc',args.cc),('clang',args.clang),('host-clang',args.host_clang)]:
            path=Path(shutil.which(tool)).resolve();report['tools'][name]={"path":str(path),"sha256":sha(path)}
            must([path,'--version'],name+'-version')
        flags=['-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-I'+str(HERE)]
        must([args.cc,*flags,'-DORACLE_MAIN',out/'oracle.c','-o',out/'oracle'],'oracle-build')
        must([out/'oracle'],'oracle-run');layout=json.loads((out/'oracle-run.log').read_text());report['actual_declaration_oracle']=layout
        if layout!=profile['actual_declaration_oracle']:raise ValueError('Actual source declaration oracle differs from pinned profile')
        sanitize=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer']
        must([args.host_clang,'-print-runtime-dir'],'host-runtime-directory')
        runtime=Path((out/'host-runtime-directory.log').read_text().strip())
        report['host_runtime_archives']={str(f):sha(f) for f in (runtime/'libclang_rt.asan.a',runtime/'libclang_rt.asan_static.a')}
        must([args.host_clang,*sanitize,'-###',HERE/'sanitizer_controls.c','-o',out/'link-plan-only'],'host-runtime-link-plan')
        must([args.host_clang,*flags,*sanitize,HERE/'pcm_host.c',HERE/'test_host.c',out/'oracle.c','-o',out/'host-tests'],'host-build')
        must([out/'host-tests'],'host-run');report['host_result']=json.loads((out/'host-run.log').read_text())
        must([args.host_clang,*flags,*sanitize,HERE/'sanitizer_controls.c','-o',out/'sanitizer-controls'],'controls-build')
        for name,arg,expected in [('asan-control','a','AddressSanitizer: heap-buffer-overflow'),('ubsan-control','u','runtime error: signed integer overflow')]:
            r=run([out/'sanitizer-controls',arg],out,name);records.append(r)
            if r['exit_code']==0 or expected not in (out/(name+'.log')).read_text():raise RuntimeError(name+' instrumentation was not demonstrated')
        header=cache/'include/sound/samsung/abox_ipc.h';values=layout['layout']
        expressions=['sizeof(ABOX_IPC_MSG)','sizeof(struct IPC_PCMTASK_MSG)','sizeof(struct PCMTASK_SET_BUFFER)',
          'sizeof(struct PCMTASK_HW_PARAMS)','__builtin_offsetof(ABOX_IPC_MSG,msg.pcmtask.param)',
          '__builtin_offsetof(ABOX_IPC_MSG,msg.pcmtask.param.setbuff.phys)','IPC_PCMPLAYBACK','IPC_PCMCAPTURE',
          'PCM_SET_BUFFER','PCM_PLTDAI_HW_PARAMS','PCM_PLTDAI_POINTER','PCM_PLTDAI_CLOSED']
        target_source='#include "'+str(header)+'"\n'+''.join('_Static_assert('+e+'=='+str(v)+',"genuine source layout");\n' for e,v in zip(expressions,values))
        target_source+='const unsigned long long source_layout[]={'+','.join(expressions)+'};\n';(out/'target-layout.c').write_text(target_source)
        objects=[]
        for label,target in [('elf','aarch64-none-elf'),('macho','arm64-apple-macos12')]:
            for name,file in [('adapter',HERE/'pcm_host.c'),('source-layout',out/'target-layout.c')]:
                obj=out/(name+'-'+label+'.o')
                must([args.clang,'--target='+target,'-std=c11','-O1','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror',
                      '-I'+str(HERE),'-c',file,'-o',obj],name+'-'+label)
                header_bytes=obj.read_bytes()[:32]
                if label=='elf':
                    if header_bytes[:6]!=b'\x7fELF\x02\x01' or int.from_bytes(header_bytes[18:20],'little')!=183:
                        raise ValueError('Actual target object is not little-endian AArch64 ELF64')
                elif header_bytes[:8]!=b'\xcf\xfa\xed\xfe\x0c\x00\x00\x01' or int.from_bytes(header_bytes[12:16],'little')!=1:
                    raise ValueError('Actual target object is not arm64 Mach-O MH_OBJECT')
                objects.append({'path':str(obj),'sha256':sha(obj),'size':obj.stat().st_size,
                                'verified_format':'aarch64-elf64' if label=='elf' else 'arm64-macho-object'})
        report['target_objects']=objects;report['outcome']='pass'
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as err:report['error']=str(err)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','error','host_result','device_executed','native_audio_qualified']},indent=2))
    return 0 if report['outcome']=='pass' else 2


if __name__=='__main__':raise SystemExit(main())
