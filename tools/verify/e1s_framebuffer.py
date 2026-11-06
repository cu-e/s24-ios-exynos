#!/usr/bin/env python3
"""Prepare actual framebuffer C controls and <=6 commands; never compile/run."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def prepare(root, main, out, cc):
    config_path=root/'fixtures/public/e1s-framebuffer/upstream.json';config=json.loads(config_path.read_text())
    patches=[main/config['memory_patch'],root/config['display_patch']]
    for key,path in zip(['memory_patch_sha256','display_patch_sha256'],patches):
        if sha(path)!=config[key]:raise ValueError('Exact accepted patch identity required')
    if out.exists() or out.is_symlink() or out.parent.resolve()!=out.parent:raise ValueError('Fresh canonical output with existing parent required')
    out.mkdir();commands=[]
    for variant in ['baseline','patched']:
        work=out/variant;work.mkdir()
        for name,pins in config['sources'].items():
            source=main/'references/s24-port'/name
            if sha(source)!=pins['donor_sha256']:raise ValueError('Pinned donor changed: '+name)
            target=work/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        for patch in patches[:1 if variant=='baseline' else 2]:
            for flags in [['--check'],[]]:
                argv=['git','apply',*flags,str(patch)];result=subprocess.run(argv,cwd=work,capture_output=True,text=True,timeout=15)
                commands.append({'argv':argv,'cwd':str(work),'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
                if result.returncode:raise ValueError('Patch overlay did not apply')
        for name,pins in config['sources'].items():
            if sha(work/name)!=pins['memory_baseline_sha256' if variant=='baseline' else 'display_sha256']:raise ValueError('Prepared source mismatch: '+name)
        loader=(work/'shim/e1s-xnu/loader.c').read_text()
        macros=''.join(line for line in loader.splitlines(True) if line.startswith('#define FB_'))
        declarations=loader[loader.index('static uint64_t fb_base'):loader.index('static inline void wr32')]
        functions=loader[loader.index('static void fb_flush(void)'):loader.index('static int cmdline_hold')]
        (work/'loader_ui.inc').write_text(macros+declarations+functions)
        shutil.copyfile(root/'fixtures/public/e1s-framebuffer/controls.c',work/'controls.c')
    loader=(out/'patched/shim/e1s-xnu/loader.c').read_text()
    if 'FB_BASE' in loader or 'ui_init();' in loader or 'ui_init(have_fb);' not in loader:raise ValueError('Guessed/unconditional CPU UI path remains')
    if 'if (ui_ready)\n\t\tclean(' not in loader or 'ba->Video.v_display = ui_ready ? 1 : 0;' not in loader:raise ValueError('Headless flush/video guard missing')
    resource=cc.parent.parent/'lib/clang/18';runtimes=[resource/'lib/x86_64-unknown-linux-gnu'/n for n in ['libclang_rt.asan.a','libclang_rt.asan_static.a','libclang_rt.asan-preinit.a','libclang_rt.ubsan_standalone.a']]
    if not all(p.is_file() for p in runtimes):raise ValueError('Qualified GNU-host sanitizer runtimes missing')
    host=['--target=x86_64-unknown-linux-gnu','-resource-dir='+str(resource),'-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Wall','-Wextra','-Werror']
    target=['--target=aarch64-none-elf','-O2','-g0','-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-pic','-fno-zero-initialized-in-bss','-mstrict-align','-mgeneral-regs-only','-Wall','-Wextra']
    plan=[]
    for variant in ['baseline','patched']:
        work=out/variant;source=work/'shim/e1s-xnu'
        plan.append({'id':variant+'-compile','argv':[str(cc),*host,'-I'+str(source),'-I'+str(work),str(work/'controls.c'),str(source/'fdt.c'),str(source/'ui.c'),'-o',str(work/'controls')],'cwd':str(work)})
        plan.append({'id':variant+'-controls','argv':[str(work/'controls')]+(['--legacy'] if variant=='baseline' else []),'cwd':str(work)})
    source=out/'patched/shim/e1s-xnu'
    plan.append({'id':'loader-freestanding','argv':[str(cc),*target,'-c',str(source/'loader.c'),'-o',str(out/'loader.aarch64.o')],'cwd':str(source)})
    plan.append({'id':'fdt-ui-freestanding','argv':[str(cc),*target,'-c',str(source/'fdt.c'),str(source/'ui.c')],'cwd':str(source)})
    inputs={str(p):sha(p) for p in out.rglob('*') if p.is_file()};inputs.update({str(p):sha(p) for p in [cc,*patches,config_path,Path(__file__).resolve(),*runtimes]})
    record={'schema':'e1s-framebuffer-focused-plan-v1','task':'STR-005','owner':'codex-e1s-framebuffer-20261106-sr5','phase':'planned-not-executed','max_jobs':1,'max_owned_rss_bytes':256*1024**2,'child_timeout_seconds':120,'whole_timeout_seconds':600,'sanitizer_requires_RSS_only_no_small_RLIMIT_AS':True,'hardware_or_target_execution':False,'commands':plan,'input_sha256':inputs,'source_witness':config,'preparation_commands':commands}
    (out/'plan.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'phase':record['phase'],'plan':str(out/'plan.json'),'sha256':sha(out/'plan.json'),'commands':len(plan)}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--main',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--cc',type=Path,required=True);a=p.parse_args();prepare(Path(__file__).resolve().parents[2],a.main.resolve(),a.out.absolute(),a.cc.resolve())

if __name__=='__main__':main()
