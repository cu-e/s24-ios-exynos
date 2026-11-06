#!/usr/bin/env python3
"""Prospectively registered VM048 controls. Synthetic images never qualify."""
import argparse
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
START = time.monotonic()


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def module(name,path):
    spec = importlib.util.spec_from_file_location(name,path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def guard():
    require(time.monotonic()-START < 90, 'Control batch deadline exceeded')
    available = next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
    require(available >= 4*1024**3, 'Control batch below4GiB memory floor')


def synthetic_image(tool,core,paths,out,counts=(2,2)):
    """Source-derived test framing, copied genuine records/cstrings; NOT linked."""
    base = 0xfffffff007004000
    strings = bytearray()
    payloads = []
    for ident,kind,count in [('osdata','fixed',counts[0]),('osarray','variable',counts[1])]:
        with core.macho_snapshot(paths[ident]) as (snapshot,view):
            section = next(s for s in view['sections'] if s['name'] == tool.LAYOUTS[kind]['section'])
            target = next(s for s in view['sections'] if s['name'] == '__cstring')
            string_offset = len(strings)
            strings.extend(snapshot.read_range(target['offset'],target['size']))
            data = bytearray(snapshot.read_range(section['offset'],tool.LAYOUTS[kind]['stride']*count))
            resolved = tool.pointer_relocations(snapshot,view,section,tool.LAYOUTS[kind],core.macho_symbol)
            for at,row in resolved.items():
                if at >= len(data) or row['target_address'] == 0:
                    continue
                pointer = base+0x2000+string_offset+row['target_address']-target['address']
                struct.pack_into('<Q',data,at,pointer)
            payloads.append(data)
    require(len(strings) <= 0x2000, 'Synthetic copied cstrings exceed test slot')
    data = bytearray(0x6000)
    data[0x2000:0x2000+len(strings)] = strings
    fixed_offset,var_offset = 0x4000,0x4000+len(payloads[0])
    data[fixed_offset:var_offset] = payloads[0]
    data[var_offset:var_offset+len(payloads[1])] = payloads[1]
    def section(name,segment,address,size,offset,align,flags):
        return struct.pack('<16s16sQQ8I',name.encode(),segment.encode(),address,size,offset,align,0,0,flags,0,0,0)
    def segment(name,address,size,offset,stored,protection,sections):
        return struct.pack('<II16s4Q4I',25,72+80*len(sections),name.encode(),address,size,offset,stored,
                           protection,protection,len(sections),0)+b''.join(sections)
    commands = [segment('__TEXT',base,0x4000,0,0x4000,5,[
        section('__text','__TEXT',base+0x1000,4,0x1000,2,0x80000400),
        section('__cstring','__TEXT',base+0x2000,len(strings),0x2000,0,2)]),
        segment('__DATA_CONST',base+0x4000,0x1000,0x4000,0x1000,1,[
        section('__kalloc_type','__DATA_CONST',base+fixed_offset,len(payloads[0]),fixed_offset,3,0x08000000),
        section('__kalloc_var','__DATA_CONST',base+var_offset,len(payloads[1]),var_offset,3,0x08000000)])]
    names = [('__start',1,base+0x1000)]
    for kind,ordinal,offset,payload in [('fixed',3,fixed_offset,payloads[0]),('variable',4,var_offset,payloads[1])]:
        for edge,value in [('start',base+offset),('end',base+offset+len(payload))]:
            names.append(('section$'+edge+'$__DATA_CONST$'+tool.LAYOUTS[kind]['section'],ordinal,value))
    nlists,table = bytearray(),bytearray(b'\0')
    for name,ordinal,value in names:
        nlists.extend(struct.pack('<IBBHQ',len(table),15,ordinal,0,value));table.extend(name.encode()+b'\0')
    symoff,stroff = 0x5000,0x5000+len(nlists)
    commands.append(struct.pack('<6I',2,24,symoff,len(names),stroff,len(table)))
    thread = bytearray(288);struct.pack_into('<4I',thread,0,5,288,6,68);struct.pack_into('<Q',thread,16+32*8,base+0x1000)
    commands.append(thread)
    body = b''.join(commands)
    struct.pack_into('<8I',data,0,0xfeedfacf,0x100000c,0,2,len(commands),len(body),0,0)
    data[32:32+len(body)] = body;data[symoff:stroff] = nlists;data[stroff:stroff+len(table)] = table
    path = out/'synthetic-linked-layout.macho';path.write_bytes(data)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args();out = args.out.resolve();main_root = args.main.resolve()
    require(out.is_relative_to(ROOT/'docs/procedures/avf-allocator-retention') and not out.exists(), 'Fresh scoped output required')
    out.mkdir(parents=True)
    report = dict(task='VM-048',owner='codex-guest-allocator-witness-20261106-fc',experiment='VM048RETENTION-001',
                  kind='host-test',recorded_at=datetime.now(timezone.utc).isoformat(),argv=sys.argv,outcome='fail',
                  checks=[],compiler_executed=False,linker_executed=False,external_section_tool_executed=False,
                  guest_executed=False,actual_final_image_measured=False,full_kernel_retention_qualified=False)
    inputs = json.loads((ROOT/'fixtures/public/avf-allocator-retention/inputs.json').read_text())
    report['fixture_sha256'] = sha(ROOT/'fixtures/public/avf-allocator-retention/inputs.json')
    report['checker_sha256'] = sha(Path(__file__))
    code = 0
    def check(name,value,**facts):
        guard();require(value,'Control failed: '+name);report['checks'].append(dict(name=name,pass_result=True,**facts))
    def rejects(name,action):
        guard()
        try:action()
        except ValueError as error:report['checks'].append(dict(name=name,pass_result=True,rejection=str(error)))
        else:raise ValueError('Corruption unexpectedly accepted: '+name)
    try:
        for _ in range(3):guard()
        core_path = main_root/inputs['cu_core']['path']
        require(sha(core_path) == inputs['cu_core']['sha256'],'Exact frozen CU core required')
        core = module('vm048_cu',core_path)
        tool = module('vm048_retention',ROOT/'tools/build/avf_guest_allocator_retention.py')
        report['core_sha256'] = sha(core_path);report['tool_sha256'] = tool.tool_sha256()
        with ExitStack() as stack:
            sources = {k:stack.enter_context(core.CoherentFile(main_root/v['path'])) for k,v in inputs['source_files'].items()}
            source = tool.source_contract(sources)
        report['source_contract'] = source
        check('source-derived-fixed64-variable80-and22zones',source['layouts']['fixed']['stride'] == 64 and source['layouts']['variable']['stride'] == 80 and source['variable_zones'] == 22)
        bad = deepcopy(source);bad['layouts']['variable']['stride'] = 88
        rejects('invented-variable-layout',lambda:tool.check_source(bad))
        paths = {}
        for item in inputs['witnesses']:
            paths[item['id']] = main_root/item['path']
            check('exact-real-'+item['id'],sha(paths[item['id']]) == item['sha256'],sha256=item['sha256'])
        for ident,item in inputs['provenance'].items():
            path = main_root/item['path']
            require(path.stat().st_size <= 1024**2, 'Bounded historical object receipt required')
            check('historical-compile-receipt-'+ident,sha(path) == item['sha256'])
            receipt = json.loads(path.read_text())
            if ident == 'osarray':
                row = receipt
                require(row['outcome'] == 'pass' and row['command']['exit_code'] == 0,'Historical OSArray compile failed')
                require('-DXNU_NO_TYPE_BUILTINS=0' in row['command']['argv'],'Historical OSArray disabled metadata')
            else:
                expected_id = {'osdata':'libkern/OSData.cpo','kalloc':'osfmk/kalloc.o'}[ident]
                row = next(r for r in receipt['representative_compiles'] if r['id'] == expected_id)
                require(row['exit_code'] == 0 and row['actual_arm64_object'],'Historical compile did not produce ARM64')
            check('historical-source-object-binding-'+ident,
                  Path(row['object']) == paths[ident] and row['object_sha256'] == sha(paths[ident]) and
                  row['source_sha256'] == sha(Path(row['source'])),source_sha256=row['source_sha256'])
        check('historical-OSArray-raw-receipt-only',sha(main_root/inputs['historical_osarray_raw']['path']) == inputs['historical_osarray_raw']['sha256'])
        witnesses = {}
        views = {}
        for ident in ('osdata','osarray'):
            with core.macho_snapshot(paths[ident]) as (snapshot,view):
                witnesses[ident] = tool.inspect_object(snapshot,view,source,symbol_at=core.macho_symbol)
                views[ident] = {k:v for k,v in view.items() if k != 'external_symbols'}
            check('real-'+ident+'-three-records',sum(r['count'] for r in witnesses[ident]['metadata_records'].values()) == 3)
        report['actual_object_witnesses'] = witnesses
        with core.macho_snapshot(paths['kalloc']) as (snapshot,view):
            boundaries = tool.boundary_references(snapshot,view,symbol_at=core.macho_symbol)
        check('real-kalloc16refs-four-boundaries',sum(boundaries['counts'].values()) == 16 and set(boundaries['counts'].values()) == {4},evidence=boundaries)
        def object_copy(label,ident,change):
            require(paths[ident].stat().st_size < 1024**2,'Bounded actual object copy required')
            data = bytearray(paths[ident].read_bytes());change(data)
            path = out/(label+'.cpo');path.write_bytes(data)
            return path
        def inspect(path):
            with core.macho_snapshot(path) as (snapshot,view):
                return tool.inspect_object(snapshot,view,source,symbol_at=core.macho_symbol)
        fixed = next(s for s in views['osdata']['sections'] if s['name'] == '__kalloc_type')
        var = next(s for s in views['osarray']['sections'] if s['name'] == '__kalloc_var')
        def integer(offset,value,size=8):return lambda b:b.__setitem__(slice(offset,offset+size),value.to_bytes(size,'little',signed=value<0))
        positive = object_copy('real-signature-plus1','osdata',integer(fixed['offset']+32,1))
        changed = inspect(positive)
        check('nonzero-inline-signature-substring',any(r['record']['signature'] == '2' for r in changed['metadata_records'].values()))
        # Negative inline addend is balanced by advancing the genuine string
        # symbol one byte: same selected real name, independently decoded nlist.
        with core.macho_snapshot(paths['osdata']) as (snapshot,view):
            relocation = next(r for r in tool.relocations(snapshot,fixed) if r['address'] == 16)
            symbol = core.macho_symbol(snapshot,view,relocation['index'])
            nlist_value = view['symbol_table']['offset']+16*relocation['index']+8
        def negative_inline(data):
            for offset in (16,80,144):integer(fixed['offset']+offset,-1)(data)
            integer(nlist_value,symbol['value']+1)(data)
        negative = inspect(object_copy('real-negative-inline-compensated','osdata',negative_inline))
        check('negative-inline-addend-resolves-same-name',negative['metadata_records'] == witnesses['osdata']['metadata_records'] and any(p['inline_addend'] == -1 for p in negative['pointers']))
        mutations = [
            ('name-plus1','osdata',integer(fixed['offset']+16,1)),
            ('inline-outside','osdata',integer(fixed['offset']+16,2**62)),
            ('missing-live-support','osdata',integer(fixed['segment_name_offset']-16+64,0,4)),
            ('fixed-stride','osdata',integer(fixed['segment_name_offset']-16+40,191,8)),
            ('variable-version','osarray',integer(var['offset'],2,2)),
            ('variable-reserved','osarray',integer(var['offset']+24,1)),
            ('runtime-flags','osdata',integer(fixed['offset']+40,0x8060,4)),
            ('missing-relocations','osdata',integer(fixed['segment_name_offset']-16+60,0,4)),
        ]
        for label,ident,change in mutations:
            path = object_copy(label,ident,change);rejects('real-copy-'+label,lambda p=path:inspect(p))
        actual_bits = struct.unpack('<I',paths['osdata'].read_bytes()[fixed['relocation_offset']+4:fixed['relocation_offset']+8])[0]
        for label,bits in [('unsupported-type',actual_bits|(1<<28)),('pcrel',actual_bits|(1<<24)),
                           ('narrow-pointer',(actual_bits&~(3<<25))|(2<<25)),('local-target',actual_bits&~(1<<27)),
                           ('bad-symbol-index',(actual_bits&~0xffffff)|0xffffff)]:
            path = object_copy(label,'osdata',integer(fixed['relocation_offset']+4,bits,4))
            rejects('real-copy-'+label,lambda p=path:inspect(p))
        # Preserve historical ARM64_ADDEND pair regression using real kalloc.
        with core.macho_snapshot(paths['kalloc']) as (snapshot,view):
            pair_section = next(s for s in view['sections'] if any(r['type'] == 10 for r in tool.relocations(snapshot,s)))
            pair_index = next(i for i,r in enumerate(tool.relocations(snapshot,pair_section)) if r['type'] == 10)
        path = object_copy('bad-addend-pair','kalloc',integer(pair_section['relocation_offset']+(pair_index+1)*8,0x7fffffff,4))
        def consume(path):
            with core.macho_snapshot(path) as (s,v):return tool.boundary_references(s,v,symbol_at=core.macho_symbol)
        rejects('real-ARM64-addend-pair-corruption',lambda:consume(path))
        image = synthetic_image(tool,core,paths,out)
        required = []
        for witness in witnesses.values():
            for fingerprint,row in witness['metadata_records'].items():
                required.append(dict(object_sha256=[witness['object_sha256']],fingerprint=fingerprint,minimum=1,
                                     liveness_proof_sha256=hashlib.sha256(b'SYNTHETIC CONTROL ONLY, NOT REAL LIVENESS').hexdigest()))
        contract = dict(source=source,selection=dict(use_lto=False,dead_strip=False,pointer_encoding='unslid-u64',kc_format='static'),
                        witnesses=list(witnesses.values()),required=required)
        def validate(path,request=None):
            with core.macho_snapshot(path,image=True) as (s,v):return tool.validate(s,v,contract if request is None else request,symbol_at=core.macho_symbol)
        final = validate(image)
        check('synthetic-required-subset-no-input-output-equality-or-linker-credit',sum(s['count'] for s in final['sections']) == 4 and final['required_retention'] == 'pass' and final['product_qualification'] == 'not-granted-by-byte-validator')
        json.dumps(final)  # after snapshot/index closure: only detached primitives
        report['synthetic_parser_result'] = final
        empty = deepcopy(contract);empty['required'] = []
        check('empty-required-cannot-complete-retention',validate(image,empty)['required_retention'].startswith('incomplete'))
        missing = deepcopy(contract);missing['required'][0]['minimum'] = 3
        rejects('synthetic-missing-required-duplicate',lambda:validate(image,missing))
        for label,alter in [('unsupported-fileset',lambda c:c['selection'].__setitem__('kc_format','fileset')),
                            ('unqualified-LTO-branch',lambda c:c['selection'].__setitem__('use_lto',True)),
                            ('unqualified-dead-strip-branch',lambda c:c['selection'].__setitem__('dead_strip',True)),
                            ('authenticated-pointer',lambda c:c['selection'].__setitem__('pointer_encoding','arm64e')),
                            ('false-source-layout',lambda c:c['source']['layouts']['fixed'].__setitem__('stride',32)),
                            ('no-proof',lambda c:c['required'][0].__setitem__('liveness_proof_sha256','')),
                            ('unwitnessed-record',lambda c:c['required'][0].__setitem__('fingerprint','0'*64)),
                            ('wrong-tool',lambda c:c['witnesses'][0].__setitem__('tool_sha256','0'*64)),
                            ('duplicate-witness-credit',lambda c:c['witnesses'].append(c['witnesses'][0])),
                            ('duplicate-required-source-credit',lambda c:c['required'][0]['object_sha256'].append(c['required'][0]['object_sha256'][0]))]:
            bad = deepcopy(contract);alter(bad);rejects(label,lambda c=bad:validate(image,c))
        with core.macho_snapshot(image,image=True) as (snapshot,view):
            constant = next(s for s in view['sections'] if s['name'] == '__kalloc_type')
            symbol_value_at = view['symbol_table']['offset']+2*16+8 # fixed end
            const_segment_at = 32+(72+2*80)
            final_name_offset = struct.unpack('<Q',snapshot.read_range(constant['offset']+16,8))[0]-0xfffffff007004000
        def image_copy(label,change):
            data = bytearray(image.read_bytes());change(data);p = out/(label+'.macho');p.write_bytes(data);return p
        for label,change in [
            ('final-pointer-unmapped',integer(constant['offset']+16,0x1234)),
            ('final-end-mismatch',integer(symbol_value_at,constant['address']+constant['size']-8)),
            ('final-short-stride',integer(constant['segment_name_offset']-16+40,constant['size']-8)),
            ('final-writable-data-const',integer(const_segment_at+60,3,4)),
            ('final-under-aligned',integer(constant['segment_name_offset']-16+52,2,4)),
            ('final-string-corruption',integer(final_name_offset,255,1)),
            ('final-nonzero-runtime-field',integer(constant['offset'],1)),
            ('final-runtime-reloc',integer(constant['segment_name_offset']-16+60,1,4)),
        ]:
            path = image_copy(label,change);rejects(label,lambda p=path:validate(p))
        def append_command(data,command):
            count,size = struct.unpack_from('<II',data,16)
            data[32+size:32+size+len(command)] = command
            struct.pack_into('<II',data,16,count+1,size+len(command))
        for label,command in [
            ('chained-fixups',struct.pack('<4I',0x80000034,16,0,0)),
            ('dyld-rebases',struct.pack('<12I',0x80000022,48,0x1000,1,0,0,0,0,0,0,0,0)),
            ('dynamic-relocs',struct.pack('<20I',0xb,80,*([0]*15+[1,0,0]))),
        ]:
            path = image_copy(label,lambda b,c=command:append_command(b,c));rejects(label,lambda p=path:validate(p))
        # Bounded lifecycle adversaries operate on owned copies only.
        for label,change in [('fd-growth',lambda p:p.open('ab').write(b'x')),
                             ('fd-truncation',lambda p:os.truncate(p,64)),
                             ('path-swap',lambda p:os.replace(image_copy('replacement',lambda b:None),p))]:
            p = image_copy(label,lambda b:None)
            def attacked(p=p,change=change):
                with core.macho_snapshot(p,image=True) as (s,v):
                    change(p);return tool.validate(s,v,contract,symbol_at=core.macho_symbol)
            rejects(label,attacked)
        link = out/'scratch-symlink';link.symlink_to(image)
        try:
            with core.CoherentFile(link):raise ValueError('Symlink unexpectedly opened')
        except OSError:
            check('nofollow-symlink',True)
        fd_before = len(list(Path('/proc/self/fd').iterdir()))
        for _ in range(20):
            validate(image)
            rejects('repeat-error-cleanup',lambda:validate(image,missing))
        check('snapshot-index-no-FD-growth',len(list(Path('/proc/self/fd').iterdir())) == fd_before,fd_count=fd_before)
        report['artifact_sha256'] = {str(p.relative_to(out)):sha(p) for p in out.iterdir() if p.is_file() and not p.is_symlink()}
        status = Path('/proc/self/status').read_text().splitlines()
        report['process_status'] = {x.split(':',1)[0]:x.split(':',1)[1].strip() for x in status if x.startswith(('VmHWM:','VmRSS:'))}
        hwm = int(report['process_status']['VmHWM'].split()[0])*1024
        check('current-image-HWM-below256MiB',hwm <= 256*1024**2,bytes=hwm)
        report['outcome'] = 'pass'
    except Exception as error:
        code = 2;report['error'] = repr(error)
    report['elapsed_seconds'] = time.monotonic()-START;report['exit_code'] = code
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ('outcome','exit_code','error','elapsed_seconds','process_status')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
