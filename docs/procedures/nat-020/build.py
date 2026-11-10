#!/usr/bin/env python3
"""Build a new local candidate. Host only; never opens a phone or writes a partition."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, shutil, struct, subprocess, sys

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BASE=ROOT/'artifacts/nat-006/build-002'
KERNEL=ROOT/'worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001/kernel/kernel.unstripped'
KERNEL_SHA='4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f'
CMDLINE='rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT020-83s debug=0xc serial=3 cpus=1 keepsyms=1 -v'

def sha(b): return hashlib.sha256(b).hexdigest()

def macho(raw):
    assert struct.unpack_from('<I',raw)[0]==0xfeedfacf
    segments=[]; symbols={}; off=32; symtab=None
    for _ in range(struct.unpack_from('<I',raw,16)[0]):
        cmd,size=struct.unpack_from('<II',raw,off)
        assert size>=8 and off+size<=len(raw)
        if cmd==0x19:
            name=raw[off+8:off+24].split(b'\0')[0].decode()
            vm,vs,fo,fs=struct.unpack_from('<4Q',raw,off+24)
            segments.append((name,vm,vs,fo,fs))
        if cmd==2: symtab=struct.unpack_from('<4I',raw,off+8)
        off+=size
    assert symtab
    so,ns,st,ss=symtab
    assert so+16*ns<=len(raw) and st+ss<=len(raw)
    for i in range(ns):
        no,t,section,desc,value=struct.unpack_from('<IBBHQ',raw,so+i*16)
        if t&0xe0 or t&0xe!=0xe: continue
        end=raw.find(b'\0',st+no,st+ss)
        assert end>=0
        name=raw[st+no:end].decode()
        # Data symbols are deliberately excluded from the patch map.
        seg=next((s for s in segments if s[0]=='__TEXT_EXEC' and s[1]<=value<s[1]+s[4]),None)
        if seg: symbols[name]=(value,seg[3]+value-seg[1])
    return segments,symbols

def deny_storage(raw):
    """Explicit return stubs in an exact, project-linked kernel; no layout changes.

    These block E1S's driver and the separately linked Redwood/loader mailbox
    driver. They are additional containment, not hardware isolation or a proof
    that arbitrary kernel faults could never corrupt memory.
    """
    assert sha(raw)==KERNEL_SHA, 'base linked kernel identity changed'
    segs,symbols=macho(raw)
    returns={
      '_e1s_ufs_probe':0, '_e1s_ufs_rootdev':6,
      '_e1s_ufs_command_retry':6, '_e1s_ufs_legacy_init':6, '_e1s_ufs_mcq_init':6,
      '_e1s_ufs_open':6, '_e1s_ufs_read':6, '_e1s_ufs_write':30,
      '_e1s_ufs_bioctl':6, '_e1s_ufs_cioctl':6, '_e1s_ufs_psize':-1,
      '_redwood_ufs_init':0, '_redwood_ufs_quiesce':0,
      '_ufs_open':6, '_ufs_copen':6, '_ufs_read':6, '_ufs_cread':6,
      '_ufs_cwrite':30, '_ufs_request':6, '_ufs_native_map':6,
      '_ufshc_probe':0, '_ufshc_available':0, '_ufshc_list_in':0,
      '_ufshc_read':6, '_ufshc_switch_in':6, '_ufshc_switch_out':6,
      '_ufshc_set_luns':0, '_ufshc_report':0, '_ufshc_permitted':0,
    }
    assert not any('sweet_ufs' in n for n in symbols), 'unreviewed extra UFS driver'
    out=bytearray(raw); patches=[]; allowed=set()
    addresses=sorted(set(v for v,o in symbols.values()))
    for name,result in returns.items():
        assert name in symbols, 'missing required symbol '+name
        va,fo=symbols[name]
        next_va=next(v for v in addresses if v>va)
        assert next_va-va>=8 and fo%4==0, 'stub overlaps next symbol'
        # MOV W0,#errno (or MOVN W0,#0), RET. No stack, memory, branch or MMIO.
        first=0x12800000 if result==-1 else 0x52800000|(result<<5)
        stub=struct.pack('<II',first,0xd65f03c0)
        before=raw[fo:fo+8]
        out[fo:fo+8]=stub; allowed.update(range(fo,fo+8))
        patches.append(dict(symbol=name,va=hex(va),file_offset=fo,
                            before=before.hex(),after=stub.hex(),return_value=result))
    changed={i for i,(a,b) in enumerate(zip(raw,out)) if a!=b}
    assert changed<=allowed and len(raw)==len(out)
    return bytes(out),dict(base_sha256=sha(raw),derived_sha256=sha(out),patches=patches,
                          changed_bytes=len(changed),layout_unchanged=True,
                          limitation='Static entry-point containment, not hardware memory isolation.')

def replace_once(text,old,new):
    assert text.count(old)==1, 'source anchor mismatch: '+old[:70]
    return text.replace(old,new,1)

def diagnostics(src):
    p=src/'shim/e1s-xnu/loader.c'; s=p.read_text()
    s=replace_once(s,'\tif (pos >= LOG_MAX)\n\t\treturn;',
      '\tif (pos >= LOG_MAX) {\n\t\tif (loader_log.reserved != UINT32_MAX) loader_log.reserved++;\n\t\treturn;\n\t}')
    anchor='static void clean(uintptr_t start, uintptr_t end)'
    s=replace_once(s,anchor,'''/* Image RAM only: no retained-memory or USB delivery contract. */
void diagnostic_begin(void)
{
    log_init();
    log_str("NAT020-83s: safe EL1 stack/BSS reached; RAM log only\\n");
}
void diagnostic_value(const char *key, uint64_t value)
{
    uint64_t ticks;
    __asm__ volatile("mrs %0, cntpct_el0" : "=r"(ticks));
    log_kv("ticks",ticks); log_kv(key,value); log_char('\\n');
}
void diagnostic_guard_result(uint64_t value)
{
    diagnostic_value("guard_result",value);
}

'''+anchor)
    s=replace_once(s,'\tif (!fdt_validate(dtb))\n\t\treturn 0;\n\tlog_init();',
      '\tdiagnostic_value("loader_main_enter",dtb);\n\tif (!fdt_validate(dtb)) {\n\t\tdiagnostic_value("invalid_fdt",dtb);\n\t\treturn 0;\n\t}')
    s=replace_once(s,'\tlog_str("zeroing XNU RAM...\\n");',
      '\tdiagnostic_value("zero_begin",win_base);\n\tlog_str("zeroing XNU RAM...\\n");')
    s=replace_once(s,'\t\t\tzero(win_base + off, n);',
      '\t\t\tzero(win_base + off, n);\n\t\t\tdiagnostic_value("zero_bytes",off+n);')
    s=replace_once(s,'\tlog_str("\\nJUMP TO XNU\\n");',
      '\tlog_str("\\nPREPARING XNU HANDOFF (not proof of entry)\\n");')
    s=replace_once(s,'\tclean(win_base, mem_end);',
      '\tdiagnostic_value("clean_full_window_begin",win_base);\n\tclean(win_base, mem_end);\n\tdiagnostic_value("clean_full_window_end",mem_end);')
    s=replace_once(s,'\treturn entry_pa;',
      '\tdiagnostic_value("return_entry_to_assembly",entry_pa);\n\treturn entry_pa;')
    p.write_text(s)
    p=src/'shim/e1s-xnu/start.S'; s=p.read_text()
    s=replace_once(s,'3:\n\tmov\tx0, x19', '''3:
	bl	diagnostic_begin
	bl	recovery_guard
	mov	x21, x0
	bl	diagnostic_guard_result
	cbnz	x21, halt
	mov	x0, x19''')
    # Mark only the pre-clean stage; never call C after the final cache clean.
    p.write_text(s)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    commands=[]
    report=dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        kind='host-test',outcome='fail',device_used=False,flashed=False,commands=commands,
        watchdog_seconds=83,clock_hz_assumption=25600000,
        native_log_delivery_qualified=False,reset_persistence_qualified=False,
        automatic_android_return_qualified=False,cmdline=CMDLINE)
    def run(argv,cwd=ROOT):
        r=subprocess.run(list(map(str,argv)),cwd=cwd,capture_output=True,text=True,timeout=300)
        commands.append(dict(argv=list(map(str,argv)),exit_code=r.returncode,stdout=r.stdout[-6000:],stderr=r.stderr[-6000:]))
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if r.returncode: raise RuntimeError(f'command failed ({r.returncode}): {argv}; {r.stderr[-1500:]}')
        return r.stdout
    try:
        kernel,patches=deny_storage(KERNEL.read_bytes())
        (out/'kernel.no-storage').write_bytes(kernel)
        (out/'storage-patches.json').write_text(json.dumps(patches,indent=2)+'\n')
        spec=importlib.util.spec_from_file_location('nat006',ROOT/'tools/build/e1s_recovery.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        src=out/'source';shutil.copytree(BASE/'source',src)
        run([sys.executable,ROOT/'docs/procedures/nat-010/patch.py',src])
        diagnostics(src)
        for name in ['s5e9945.c','s5e9945.h']:
            shutil.copy2(ROOT/'src/native/watchdog'/name,src/'shim/e1s-xnu'/name)
        shutil.copy2(HERE/'guard.c',src/'shim/e1s-xnu/guard.c')
        ldir=out/'loader';ldir.mkdir();objects=[]
        for name in [*helper.LOADER_FILES,'guard.c','s5e9945.c']:
            obj=ldir/(name+'.o');objects.append(obj)
            run(['zig','cc','-target','aarch64-freestanding',*helper.CFLAGS,'-c',src/'shim/e1s-xnu'/name,'-o',obj])
        elf=ldir/'loader.elf';image=ldir/'Image'
        run(['zig','cc','-target','aarch64-freestanding','-static','-nostdlib','-Wl,--build-id=none',
             '-Wl,-T,'+str(src/'shim/e1s-xnu/loader.ld'),*objects,'-o',elf])
        run(['zig','objcopy','-O','binary',elf,image])
        run([sys.executable,'-I',src/'tools/e1s/fix_image.py',image])
        abs_relocs={}; header_relocs=[]
        for obj in objects:
            rows=[s for s in run(['readelf','-rW',obj]).splitlines() if 'R_AARCH64_ABS' in s]
            if obj.name=='start.S.o':
                # The Linux Image header carries its resolved image size at 0x10.
                assert len(rows)==1 and rows[0].startswith('0000000000000010 ') and '_payload_start + 0' in rows[0]
                header_relocs=rows
                continue
            if rows:abs_relocs[obj.name]=rows
        assert not abs_relocs, abs_relocs
        shutil.copy2(BASE/'e1s.adt',out/'e1s.adt')
        run([sys.executable,'-I',src/'tools/e1s/xnu/mkpayload.py',out/'kernel.no-storage',out/'e1s.adt',out/'payload.bin','--cmdline',CMDLINE])
        run([sys.executable,'-I',src/'tools/e1s/append_payload.py','--loader',image,'--payload',out/'payload.bin','--output',out/'Image.payload'])
        stock=(ROOT/helper.STOCK_RECOVERY).read_bytes()
        assert sha(stock)==helper.STOCK_RECOVERY_SHA256
        img,layout=helper.build_recovery(stock,(out/'Image.payload').read_bytes(),helper.newc_cpio([helper.PLACEHOLDER]))
        target=out/'recovery.img';target.write_bytes(img)
        restore=out/'restore';restore.mkdir()
        (restore/'recovery.img').write_bytes(stock)
        stock_tar=helper.odin_tar('recovery.img',stock)
        (restore/'recovery-stock-odin.tar').write_bytes(stock_tar)
        (restore/'SHA256SUMS').write_text(f'{sha(stock)}  recovery.img\n{sha(stock_tar)}  recovery-stock-odin.tar\n')
        verifier=out/'verifier';verifier.mkdir()
        original=(ROOT/'docs/procedures/nat-006/verify_image.py').read_text()
        derived=replace_once(original,KERNEL_SHA,sha(kernel))
        derived=replace_once(derived,'e1s.hold=10 debug=0xc serial=3 cpus=1 keepsyms=1 -v',CMDLINE)
        (verifier/'verify_image.py').write_text(derived)
        for name in ['check_loader.py','window_harness.c']:
            shutil.copy2(ROOT/'docs/procedures/nat-006'/name,verifier/name)
        run([sys.executable,'-I',verifier/'verify_image.py','--image',target,'--stock',ROOT/helper.STOCK_RECOVERY,
             '--kernel',out/'kernel.no-storage','--restore-dir',restore,'--dtb',ROOT/'devices/e1s-fdt/2026-11-10/runtime.dtb','--out',out/'verify.json'])
        report.update(outcome='pass',image=dict(path=str(target.relative_to(ROOT)),sha256=sha(img),size=len(img)),
            storage=patches,layout=layout,absolute_c_relocations=abs_relocs,image_header_relocation=header_relocs,
            verifier_derivation=dict(base_sha256=sha(original.encode()),derived_sha256=sha(derived.encode()),changes=['kernel digest','exact command line']),
            source_sha256={str(p.relative_to(src)):sha(p.read_bytes()) for p in (src/'shim/e1s-xnu').iterdir() if p.is_file()})
    except Exception as exc:
        report['error']=str(exc)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k in ['outcome','image','error']},indent=2))
    return 0 if report['outcome']=='pass' else 1

if __name__=='__main__':sys.exit(main())
