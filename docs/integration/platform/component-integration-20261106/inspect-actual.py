#!/usr/bin/env python3
"""Independent finite raw-byte inspection of measured component products."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import struct
import time

ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');HERE=Path(__file__).resolve().parent
CHECKS=[];HASHES={};CACHE={}
def req(ok,label):
    if not ok:raise ValueError(label)
    CHECKS.append(label)
def identity(s):return(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def sha(p):
    p=Path(p);key=str(p)
    if key not in CACHE:
        with p.open('rb') as f:
            before=identity(fstat(f));h=hashlib.file_digest(f,'sha256').hexdigest();req(identity(fstat(f))==before==identity(p.stat()),'stable streamed input '+p.name)
        CACHE[key]=h;HASHES[(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p))]=h
    return CACHE[key]
def fstat(f):
    import os
    return os.fstat(f.fileno())
def data(p,expected=None):
    p=Path(p)
    with p.open('rb') as f:
        before=identity(fstat(f));req(before[2]<=64*1024**2,'bounded read '+p.name);raw=f.read();req(identity(fstat(f))==before==identity(p.stat()),'stable read '+p.name)
    h=hashlib.sha256(raw).hexdigest();CACHE[str(p)]=h;HASHES[(str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p))]=h
    req(expected is None or h==expected,'frozen digest '+p.name)
    return raw
def obj(raw):
    magic,cpu,sub,filetype,ncmd,cmdbytes,flags,res=struct.unpack_from('<8I',raw)
    req(magic==0xfeedfacf and cpu==0x100000c and filetype==1,'actual ARM64 MH_OBJECT')
    req(32+cmdbytes<=len(raw),'bounded Mach-O commands');off=32;sections=[];symtab=None;version=[]
    for _ in range(ncmd):
        cmd,size=struct.unpack_from('<II',raw,off);req(size>=8 and off+size<=32+cmdbytes,'load command extent')
        if cmd==25:
            nsect=struct.unpack_from('<I',raw,off+64)[0];req(72+nsect*80<=size,'segment section array')
            for n in range(nsect):
                q=off+72+n*80;name,seg,addr,extent,position=struct.unpack_from('<16s16sQQI',raw,q)
                sections.append({'name':name.rstrip(b'\0').decode(),'segment':seg.rstrip(b'\0').decode(),'address':addr,'size':extent,'offset':position})
        if cmd==2:symtab=struct.unpack_from('<4I',raw,off+8)
        if cmd==0x32:version.append(list(struct.unpack_from('<4I',raw,off+8)))
        off+=size
    req(off==32+cmdbytes and symtab is not None,'complete commands and actual symtab')
    symoff,count,stroff,strsize=symtab;req(symoff+16*count<=len(raw) and stroff+strsize<=len(raw),'bounded symbol/string arrays')
    strings=raw[stroff:stroff+strsize];symbols=[];defined=[];strong=[];imports=[]
    for n in range(count):
        index,typ,sect,desc,value=struct.unpack_from('<IBBHQ',raw,symoff+n*16);end=strings.find(b'\0',index);req(index<strsize and end>=index,'symbol string extent')
        name=strings[index:end].decode();s={'name':name,'type':typ,'section':sect,'desc':desc,'value':value};symbols.append(s)
        if typ&0xe0 or not typ&1:continue
        if typ&14==0:imports.append(name)
        else:
            defined.append(name)
            if not desc&0x80:strong.append(name)
    req(any(v[0]==2 and v[1]==0x100500 for v in version),'actual iOS16.5 build-version load command; SDK not inferred')
    return {'cpu_subtype':sub,'build_versions':version,'defined':sorted(defined),'strong':sorted(strong),'imports':sorted(imports),'sections':sections,'symbols':symbols}
def ar(raw):
    req(raw[:8]==b'!<arch>\n','actual ar magic');off=8;members=[];toc=None
    while off<len(raw):
        req(off+60<=len(raw) and raw[off+58:off+60]==b'`\n','actual ar header extent');h=raw[off:off+60];size=int(h[48:58]);name=h[:16].decode().strip();start=off+60;end=start+size;req(end<=len(raw),'ar body extent')
        if name.startswith('#1/'):
            n=int(name[3:]);req(0<n<=min(size,4096),'positive bounded BSD name');name=raw[start:start+n].rstrip(b'\0').decode();start+=n
        else:name=name.rstrip('/')
        if name in ['__.SYMDEF','__.SYMDEF SORTED','__.SYMDEF_64','__.SYMDEF_64 SORTED']:
            req(off==8 and toc is None,'single leading real TOC');toc=(name,raw[start:end])
        else:members.append({'name':name,'offset':off,'bytes':raw[start:end]})
        off=end+(size&1)
    req(off==len(raw) and toc is not None,'complete actual archive and TOC')
    name,body=toc;width=8 if '_64' in name else 4;fmt='<Q' if width==8 else '<I';table=struct.unpack_from(fmt,body)[0];stringsize=struct.unpack_from(fmt,body,width+table)[0];strings=body[2*width+table:]
    req(table%(2*width)==0 and len(strings)==stringsize,'TOC typed extents');entries=[]
    for pos in range(width,width+table,2*width):
        index,member=struct.unpack_from('<QQ' if width==8 else '<II',body,pos);end=strings.find(b'\0',index);req(0<=index<stringsize and end>index,'TOC string range');entries.append((strings[index:end].decode(),member))
    req('SORTED' not in name or entries==sorted(entries),'real TOC sorted symbols')
    return members,entries,name
def main():
    p=argparse.ArgumentParser();p.add_argument('--component',choices=['firehose','pthread'],required=True);p.add_argument('--capsule',type=Path,required=True);p.add_argument('--sha256',required=True);p.add_argument('--run',default='1');a=p.parse_args()
    out=HERE/'runs'/('actual-'+a.component+a.run);out.mkdir(parents=True,exist_ok=False);samples=[]
    for n in range(3):
        v=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024;req(v>=4*1024**3,'stable4GiB-'+str(n));samples.append(v)
        if n<2:time.sleep(1)
    started=time.monotonic();e=json.loads(data(a.capsule,a.sha256));folder=a.capsule.parent;plan=json.loads(data(folder/'execution-plan.json'));inputs=json.loads(data(folder/'input-bindings.json'))
    req(e['outcome']=='pass' and len(e['commands'])==8 and len(e['objects'])==3,'real terminal three-TU/eight-process PASS')
    req(e['executor_sha256']==plan['executor_sha256']=='e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa','actual accepted caller')
    req(e['plan_sha256']==hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'actual canonical plan binding')
    req(all(e[k] is False for k in ['full_kernel_qualified','callback_alias_ABI_qualified','native_device_qualified','guest_executed']),'honest unqualified whole-system boundaries')
    parsed={};warnings=[];depset=set();runtimefiles=set();probe={}
    for i,c in enumerate(plan['commands']):
        loader=e['commands'][2*i];actual=e['commands'][2*i+1]
        for j,entry in enumerate([loader,actual]):
            r=entry['process'];req(r['outcome']=='pass' and r['exit_code']==0 and r['child_started'] and r['after']['owned_processes']==[] and r['after']['owned_tree_rss_bytes']==0,'actual child success and empty cleanup '+str(2*i+j))
            label=('loader-' if j==0 else 'command-')+str(i)
            stdout=data(folder/(label+'.stdout.txt'),r['stdout_sha256']).decode(errors='replace');err=data(folder/(label+'.stderr.txt'),r['stderr_sha256']).decode(errors='replace')
            if j==0:loader_text=stdout
            if err.strip():warnings.append({'label':label,'stderr':err})
        req(actual['process']['argv']==c['argv'] and actual['process']['cwd']==c['cwd'],'actual exact selected argv/CWD '+str(i))
        runtime=plan['runtime'][i];req(sha(c['argv'][0])==runtime['executable']['sha256'],'actual executable file hash '+str(i))
        mapped={}
        for line in loader_text.splitlines():
            words=line.split()
            if not words or words[0].startswith('linux-vdso'):continue
            if '=>' in words:
                req(len(words)>=3 and words[2]!='not','actual loader dependency resolves');logical=words[0];file=Path(words[2])
            else:logical=Path(words[0]).name;file=Path(words[0])
            mapped[logical]=str(file.resolve(strict=True))
        req(mapped=={name:r['resolved_path'] for name,r in actual['actual_runtime'].items()},'independent actual loader mapping '+str(i))
        for mapping in actual['actual_runtime'].values():
            req(sha(mapping['resolved_path'])==mapping['sha256'],'actual loaded runtime bytes '+Path(mapping['resolved_path']).name);runtimefiles.add(mapping['resolved_path'])
        if i==3:continue
        path=c['object'];meta=e['objects'][path];raw=data(Path(path),meta['sha256']);v=obj(raw);parsed[path]=v
        req(sorted(v['defined'])==meta['definitions'] and v['imports']==meta['imports'],'independent actual symbol table '+Path(path).name)
        dep=data(Path(meta['depfile']),meta['depfile_sha256']).decode();first=dep.replace('\\\n','').splitlines()[0];target,rest=first.split(':',1);require_target=shlex.split(target)
        req(require_target==[path],'actual dependency target '+Path(path).name)
        names={str((Path(c['cwd'])/x).resolve()) for x in shlex.split(rest)};req(names==set(meta['dependencies']),'independent actual dependency list '+Path(path).name)
        for name,expected in meta['dependencies'].items():
            req(inputs['files'].get(name)==expected==sha(name),'actual qualified dependency '+Path(name).name);depset.add(name)
        req(c['source'] in names,'real TU present in dependencies '+Path(path).name)
        if a.component=='firehose' and i in [1,2]:
            symbol=next(s for s in v['symbols'] if s['name']==('_s24_firehose_provider' if i==1 else '_s24_firehose_interface'));section=v['sections'][symbol['section']-1];n=9 if i==1 else 11;offset=section['offset']+symbol['value']-section['address'];req(section['segment']=='__DATA_CONST' and section['name']=='__s24fh' and offset+n*8<=len(raw),'actual probe file section')
            values=list(struct.unpack_from('<'+'Q'*n,raw,offset));req(values==meta['probe_record'],'independent actual target probe bytes');probe[Path(path).name]=values
    memberpaths=plan['commands'][-1]['members'];archive=Path(plan['commands'][-1]['archive']);archivebytes=data(archive,e['archive']['sha256']);members,toc,tocname=ar(archivebytes)
    req([m['name'] for m in members]==[Path(x).name for x in memberpaths],'actual exact ordered archive membership')
    for m,path in zip(members,memberpaths):req(m['bytes']==data(Path(path),e['objects'][path]['sha256']),'archive contains identical real object bytes '+m['name'])
    offsets={m['offset']:path for m,path in zip(members,memberpaths)}
    for name,offset in toc:req(offset in offsets and name in parsed[offsets[offset]]['defined'],'actual TOC points to real exported symbol '+name)
    if a.component=='firehose':req('___firehose_buffer_create' in parsed[memberpaths[0]]['strong'] and len(members)==1,'genuine strong provider and probe objects excluded')
    else:
        req({'_pthread_start','_pthread_kext_kern'}.issubset(set(parsed[memberpaths[0]]['strong'])),'actual strong remapped pthread init/provider')
        req(not any({'_pthread_kern','_current_uthread'}&set(x['defined']+x['imports']) for x in parsed.values()),'actual remapped guest namespace across all three objects')
    summary={'component':a.component,'object_sha256':{p:e['objects'][p]['sha256'] for p in parsed},'archive_sha256':e['archive']['sha256'],'archive_members':[m['name'] for m in members],'toc_name':tocname,'unique_actual_dependencies':len(depset),'actual_loaded_runtime_files':sorted(runtimefiles),'probe_records':probe,'strong_definitions':{p:v['strong'] for p,v in parsed.items()},'unresolved_imports_retained':{p:v['imports'] for p,v in parsed.items()},'nonempty_stderr':warnings}
    report={'kind':'host-test','origin':'local-host','outcome':'pass','recorded_at':datetime.now(timezone.utc).isoformat(),'task':'INT-003','owner':'codex-integrator-platform-20261106-cn','experiment':'PLATCOMPACT-001' if a.component=='firehose' else 'PLATCOMPACT-002','summary':'Independent actual '+a.component+' object/archive/runtime/dependency intake passes; source-selected compilation only, full ABI/link/runtime/hardware unqualified.','checks':len(CHECKS),'check_names':CHECKS,'result':summary,'admission_MemAvailable_bytes':samples,'elapsed_seconds':time.monotonic()-started,'proc_status':[x for x in Path('/proc/self/status').read_text().splitlines() if x.startswith(('VmHWM:','VmRSS:'))],'artifacts':list(HASHES),'artifact_sha256':HASHES,'control_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'compiler_archiver_loader_guest_executed_by_reviewer':False,'actual_queue_mutated':False,'callback_alias_ABI_full_link_native_qualified':False}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':len(CHECKS),'archive_sha256':summary['archive_sha256'],'members':summary['archive_members'],'dependencies':summary['unique_actual_dependencies'],'nonempty_stderr_files':len(warnings),'evidence_sha256':hashlib.sha256((out/'evidence.json').read_bytes()).hexdigest(),'memory':report['proc_status']}))
if __name__=='__main__':main()
