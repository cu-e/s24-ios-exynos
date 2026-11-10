#!/usr/bin/env python3
"""Inspect existing rescue incident inputs only; never invokes device tools."""
import argparse, datetime, hashlib, json, struct, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'artifacts/nat-009/check-002'
    report=json.loads((ROOT/'artifacts/nat-006/build-002/report.json').read_text())
    kernel=ROOT/report['payload']['kernel']['path']
    paths=[base/'recovery.img',base/'loader/loader.elf',base/'source/shim/e1s-xnu/loader.c',base/'source/shim/e1s-xnu/start.S',base/'source/shim/e1s-xnu/recovery_guard.c',kernel,ROOT/'patches/e1s-kernel-log/0001-image-owned-diagnostics.patch',base/'source/tools/e1s/read_log.py']
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert hashes[str((base/'recovery.img').relative_to(ROOT))]=='db19e3b775119c10431f38224c7b8eb3ecf19afd0ba96aff052f321c38d556eb'
    assert hashes[str(kernel.relative_to(ROOT))]=='4c9536d89b6ad61e49e8cc45e82820f00df4343c478d14685009ad504313595f'
    r=subprocess.run(['readelf','-sW',str(base/'loader/loader.elf')],capture_output=True,text=True,check=True)
    elf=[l.strip() for l in r.stdout.splitlines() if any(s in l for s in ['loader_log','loader_main','recovery_guard','_bss_'])]
    b=kernel.read_bytes();assert struct.unpack_from('<I',b)[0]==0xfeedfacf
    ncmds=struct.unpack_from('<I',b,16)[0];off=32;segments=[];symtab=None
    for _ in range(ncmds):
        cmd,size=struct.unpack_from('<II',b,off)
        if cmd==2:symtab=struct.unpack_from('<4I',b,off+8)
        if cmd==0x19:
            name=b[off+8:off+24].split(b'\0')[0].decode();vm,vs,fo,fs=struct.unpack_from('<4Q',b,off+24)
            segments.append(dict(name=name,vmaddr=vm,vmsize=vs,fileoff=fo,filesize=fs))
        off+=size
    assert symtab
    so,ns,st,sz=symtab;symbols=[]
    for i in range(ns):
        si,ty,se,de,v=struct.unpack_from('<IBBHQ',b,so+16*i)
        if si>=sz:continue
        name=b[st+si:b.find(b'\0',st+si,st+sz)].decode(errors='replace')
        if any(t in name for t in ['e1s_log','e1s_boot_marker']):symbols.append(dict(name=name,type=ty,section=se,address=hex(v)))
    result=dict(recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),evidence_kind='source-review',hardware_execution=False,sha256=hashes,loader_elf_symbols=elf,kernel_symbols=symbols,kernel_segments=segments,notes=['Source and binary identity/placement only. No runtime log was recovered.','Loader record is image data, reset by loader_main; earliest assembly and recovery_guard execute before log_init.','Kernel image-owned ring/marker source overlay has no reset persistence ABI; exact emitted symbols are listed without assuming runtime execution.'])
    (a.out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(loader_symbols=elf,kernel_symbols=symbols),indent=2))
if __name__=='__main__':main()
