#!/usr/bin/env python3
"""STR035 exact two-row changed-source admission using existing native process APIs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
W = Path(__file__).resolve().parents[3]
NATIVE = MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py'
NATIVE_SHA = '2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f'
H = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
NATIVE_RAW = NATIVE.read_bytes()
if hashlib.sha256(NATIVE_RAW).hexdigest() != NATIVE_SHA:
    raise ValueError('Changed accepted native helper')
spec = importlib.util.spec_from_file_location('kernel_log_native', NATIVE)
native = importlib.util.module_from_spec(spec)
exec(compile(NATIVE_RAW, str(NATIVE), 'exec'), native.__dict__)
module, require, digest, write = native.module, native.require, native.digest, native.write
ownership, verify, private_inputs = native.ownership, native.verify, native.private_inputs
loader_mapping, PINS = native.loader_mapping, native.PINS
CONTEXT = W/'artifacts/e1s-kernel-log-objects/source-001/source-context.json'
CONTEXT_SHA = '37923cd57d0cbeb83ab5c60c2cd2a4b8ed525965f87b3a98c79470f1fd99d58a'
PARENT_PLANS = [
    (MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/artifacts/e1s-native-compile/source-plans-005/osfmk-b-plan.json', '869495e3d8aa0910d7700ef8a07c8ee5941c04fa00b1d1d38e7c592d5970319e', 'osfmk/start.o'),
    (MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/artifacts/e1s-native-compile/source-plans-005/bsd-a-plan.json', 'fca94f18d3bd0bfa6232e2e74805408133e234beb038a2c10e13f929e883b15a', 'bsd/e1s_log.o')]


def derive(common, manifest_path, manifest_sha):
    m = common.load_project(manifest_path, manifest_sha)
    expected = dict(schema='e1s-kernel-log-two-tu-v1', task='STR-035', owner='codex-e1s-kernel-log-objects-20261106-sr35', experiment='STR035BUILD-001', partition='kernel-log-two-tu', out=str((W/'artifacts/e1s-native-compile/kernel-log-001').relative_to(MAIN)), whole_seconds=600)
    require(m == expected, 'Only original STR035 exact two-TU manifest accepted')
    out = ownership(common, m)
    local = common.load_project(CONTEXT, CONTEXT_SHA)
    overlay = common.load_project(local['source_overlay']['path'], '9cda8f05b5a1173a9f49cfdd789c347036f91451ca63abe32a08c82f4be02fda')
    source = Path(local['source_root'])
    require(source == W/'artifacts/e1s-kernel-log-objects/source-001/xnu' and source.resolve(strict=True) == source, 'Fresh local source root required')
    parent = common.load_project(overlay['parent_source_context']['path'], overlay['parent_source_context']['sha256'])
    oldfiles = common.load_project(parent['source_manifest'], overlay['parent_source_manifest_sha256'])
    require(len(oldfiles) == 5111 and local['parent_source_files'] == oldfiles, 'Exact parent source manifest required')
    newfiles = {**oldfiles, **{p:v['after_sha256'] for p,v in overlay['files'].items()}}
    require(local['source_files'] == newfiles and set(overlay['files']) == {'osfmk/arm64/start.s','bsd/dev/e1s_log.c'}, 'Only accepted2-postimage source overrides')
    metadata = local['nonsource_metadata']
    require(metadata['root'] == str(source/'.git'), 'Only own frozen non-source metadata root')
    inputs = {str(CONTEXT): H(CONTEXT), str(manifest_path): manifest_sha, str(NATIVE): NATIVE_SHA, str(Path(__file__).resolve()): H(__file__), str(local['source_overlay']['path']): local['source_overlay']['sha256']}
    inputs.update({str(source/p):h for p,h in newfiles.items()})
    inputs.update(metadata['files'])
    rows, projections, absent, lookups, loaders = [], {}, set(), {}, {}
    first = None
    for path, expected_sha, identifier in PARENT_PLANS:
        base = common.load_project(path, expected_sha)
        if first is None:
            first = base
        require(base['runtime'] == first['runtime'] and base['context'] == first['context'] and base['profile'] == first['profile'], 'Native compiler/context/profile disagreement')
        inputs.update(base['inputs']); inputs[str(path)] = expected_sha
        old = next(r for r in base['commands'] if r['id'] == identifier)
        relative = str(Path(old['source']).relative_to(Path(parent['source_root'])))
        require(newfiles[relative] == overlay['files'][relative]['after_sha256'], 'Wrong exact override source')
        mapped = lambda value: value.replace(parent['source_root'], str(source)).replace(base['out'], str(out))
        row = {**old, 'source':str(source/relative), 'source_sha256':newfiles[relative], 'argv':[mapped(a) for a in old['argv']], 'cwd':mapped(old['cwd']), 'object':mapped(old['object']), 'depfile':mapped(old['depfile'])}
        require(len(row['argv']) == (195 if identifier == 'osfmk/start.o' else 232), 'Native argv token count changed')
        rows.append(row)
        projections.update({mapped(p):v for p,v in base['projections'].items() if p.startswith(old['cwd']+'/')})
        absent.update(mapped(p) for p in base['absent_inputs'])
        lookups[row['cwd']] = native.runtime_lookup(base['runtime'], row['cwd'])
        loaders[row['cwd']] = base['loader_commands'][old['cwd']]
    # New source/header namespace and own Git inventory are explicit inputs;
    # parent inputs remain provenance, never substitutes for changed-source MD.
    result = dict(schema='e1s-native-component-plan-v1', resource_profile='project-budget-v1', **{k:m[k] for k in ['task','owner','experiment']}, shard=m['partition'], manifest=dict(path=str(manifest_path), sha256=manifest_sha), executor_sha256=H(__file__), out=str(out), whole_seconds=600, max_jobs=1, max_owned_rss_bytes=512<<20, graph=first['graph'], context=first['context'], profile=first['profile'], local_source=dict(path=str(CONTEXT), sha256=H(CONTEXT)), commands=rows, projections=projections, inputs=inputs, absent_inputs=sorted(absent), runtime=first['runtime'], nonsource_metadata=metadata, runtime_lookup=lookups, loader_commands=loaders, compiled=False)
    result['namespace'] = native.native_namespace(common, result)
    verify(common, result)
    return result


def storage(path, identifier):
    """Additional real Mach-O storage/relocation checks after common.macho()."""
    data = Path(path).read_bytes()
    require(len(data) >= 32, 'Truncated object')
    magic,cpu,subtype,kind,ncmds,nbytes,flags,reserved = struct.unpack_from('<8I',data)
    require(magic == 0xfeedfacf and cpu == 0x100000c and kind == 1 and nbytes <= len(data)-32, 'ARM64 MH_OBJECT required')
    at,end,sections,symtab = 32,32+nbytes,[],None
    for _ in range(ncmds):
        require(at+8 <= end, 'Truncated command')
        cmd,size = struct.unpack_from('<II',data,at)
        require(size >= 8 and size % 8 == 0 and size <= end-at, 'Command size')
        if cmd == 0x19:
            require(size >= 72, 'Truncated segment')
            count = struct.unpack_from('<I',data,at+64)[0]
            require(count <= (size-72)//80, 'Section count')
            for j in range(count):
                name,seg,addr,length,off,align,reloc,nreloc,attrs,*rest = struct.unpack_from('<16s16sQQ8I',data,at+72+80*j)
                zero = attrs & 255 in (1,12,18)
                require(align <= 63 and (zero or (off <= len(data) and length <= len(data)-off)) and reloc <= len(data) and nreloc <= (len(data)-reloc)//8, 'Section/relocation extent')
                sections.append(dict(name=name.split(b'\0')[0].decode(),segment=seg.split(b'\0')[0].decode(),address=addr,size=length,offset=off,align=align,zerofill=zero,reloc=reloc,nreloc=nreloc))
        elif cmd == 2:
            require(size == 24 and symtab is None, 'Symbol command')
            symtab = struct.unpack_from('<4I',data,at+8)
        at += size
    require(at == end and symtab is not None, 'Complete commands/symbols')
    off,count,strings,nstrings = symtab
    require(off <= len(data) and count <= (len(data)-off)//16 and strings <= len(data) and nstrings <= len(data)-strings, 'Symbol/string extents')
    symbols = []
    for j in range(count):
        name,typ,sect,desc,value = struct.unpack_from('<IBBHQ',data,off+16*j)
        finish = data.find(b'\0',strings+name,strings+nstrings) if name < nstrings else -1
        require(finish >= 0 and sect <= len(sections), 'Symbol bounds')
        symbols.append(dict(name=data[strings+name:finish].decode(),type=typ,section=sect,value=value))
    if identifier == 'bsd/e1s_log.o':
        matches = [s for s in symbols if s['name'] == '_e1s_log_storage' and s['type'] & 14 == 14 and s['section']]
        require(len(matches) == 1, 'Actual private ring symbol missing/duplicated')
        sym = matches[0]; sec = sections[sym['section']-1]
        require(sec['segment'] == '__DATA' and sec['align'] >= 3 and sym['value'] % 8 == 0, 'Ring writable image section/alignment')
        next_value = min([s['value'] for s in symbols if s['section'] == sym['section'] and s['type'] & 14 == 14 and s['value'] > sym['value']] + [sec['address']+sec['size']])
        require(sym['value'] >= sec['address'] and next_value-sym['value'] == 1<<20, 'Actual complete ring allocation must be1MiB')
        require(not any(s['name'] == '_ml_io_map' for s in symbols), 'Old diagnostic mapping import remains')
        return dict(ring_symbol=sym, ring_section=sec, allocation_bytes=1<<20, actual_section_is_zerofill=sec['zerofill'], final_permissions_and_mapping_deferred=True)
    targets = [(i+1,s) for i,s in enumerate(sections) if s['segment'] == '__DATA' and s['name'] == '__data' and not s['zerofill'] and s['size'] == 8 and s['align'] >= 3 and data[s['offset']:s['offset']+8] == struct.pack('<Q',0x4531534d41524b00)]
    require(len(targets) == 1, 'Actual aligned initialized8B marker section missing')
    target,marker = targets[0]; pairs = []
    for sec in sections:
        if sec['segment'] != '__TEXT' or sec['name'] != '__text':
            continue
        relocs = {}
        for j in range(sec['nreloc']):
            addr,info = struct.unpack_from('<iI',data,sec['reloc']+8*j)
            require(0 <= addr < sec['size'], 'Relocation address')
            index,external,typ = info & 0xffffff,(info>>27)&1,info>>28
            if typ not in (3,4):
                continue
            require(not external or index < len(symbols), 'Relocation symbol index')
            target_section = symbols[index]['section'] if external else index
            if target_section == target:
                require((info>>25)&3 == 2 and (info>>24)&1 == (typ == 3), 'Marker relocation encoding')
                relocs[addr] = typ
        for addr,typ in relocs.items():
            if typ != 3:
                continue
            require(relocs.get(addr+4) == 4 and addr+16 <= sec['size'], 'Marker PAGE21/PAGEOFF12 pair')
            a,b,c,d = struct.unpack_from('<4I',data,sec['offset']+addr)
            require(a & 0x9f00001f == 0x90000009 and b & 0xffc003ff == 0x91000129 and c & 0xffe0001f == 0xd280000a and d == 0xf900012a, 'Actual x9/x10 ADRP/ADD/MOVZ/STR sequence')
            pairs.append(dict(section=sec['name'],offset=addr,checkpoint=(c>>5)&0xffff,relocation_types=[3,4],instructions=[hex(v) for v in (a,b,c,d)]))
    require(sorted(p['checkpoint'] for p in pairs) == [1,2,3,4], 'Four actual marker relocation/store sequences')
    return dict(marker_section=marker,marker_bytes=8,relocation_pairs=pairs,final_signed_ADRP_range_common_4KiB_slide_and_mapping_deferred=True)

def execute(common, plan, source_plan, source_sha, approval_path, approval_sha):
    require(common.load_project(source_plan, source_sha) == plan, 'Reviewed native source plan changed')
    manifest = common.load_project(plan['manifest']['path'], plan['manifest']['sha256'])
    out = ownership(common, manifest, True)
    args = SimpleNamespace(main=MAIN, out=out, **{k:plan[k] for k in ['task','owner','experiment','shard']})
    approval = common.load_project(approval_path, approval_sha)
    require(approval['source_plan_sha256'] == source_sha, 'Wrong approved native source plan')
    budget = common.project_approval(args, approval, executor_path=Path(__file__))
    require(budget.source_plan == plan and budget.rss_limit == 512*1024**2 and budget.allocation['max_compiler_jobs_total'] == 6, 'Exact six-job/512MiB native allocation required')
    supervise = module(*PINS[2], 'native_supervisor'); core = module(*PINS[1], 'native_cleanup')
    started = time.monotonic(); reserved = False
    report = dict(kind='host-test', origin='local-host', outcome='fail', recorded_at=common.stamp(), task=plan['task'], owner=plan['owner'], experiment=plan['experiment'], source_plan_sha256=source_sha, executor_sha256=digest(__file__), commands=[], objects=[], full_kernel_qualified=False, hardware_execution=False)
    with core.owned_cancellation() as cancel:
        try:
            with cancel.cleanup():
                budget.reserve(); reserved = True
            cancel.check()
            ownership(common, manifest, True); verify(common, plan)
            require(not out.exists() and not out.is_symlink(), 'Fresh native output required; no resume')
            out.mkdir(parents=True, exist_ok=False)
            write(out/'execution-plan.json', plan); private_inputs(plan, copy=True)
            loaded = set()
            for number,row in enumerate(plan['commands']):
                cancel.check(); verify(common, plan); private_inputs(plan)
                remaining = plan['whole_seconds']-(time.monotonic()-started)
                require(remaining > 0, 'Whole native worker deadline')
                for path in [row['object'],row['depfile']]:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    require(not Path(path).exists() and not Path(path).is_symlink(), 'Output already present')
                if row['cwd'] not in loaded:
                    with cancel.command(budget):
                        record = common.run_child(plan['loader_commands'][row['cwd']], Path(row['cwd']), out, 'loader-'+str(number), supervise, timeout=min(120,remaining), admit=True, budget=budget)
                        report['commands'].append(dict(role='loader', process=record))
                    require(record.get('outcome') == 'pass' and record.get('resource_qualification') == 'pass', 'Runtime admission/observation failed')
                    loader_mapping((out/('loader-'+str(number)+'.stdout.txt')).read_text(), plan['runtime']); loaded.add(row['cwd'])
                with cancel.command(budget):
                    record = common.run_child(row['argv'], Path(row['cwd']), out, 'compile-'+str(number), supervise, timeout=min(120,max(.001,plan['whole_seconds']-(time.monotonic()-started))), admit=True, budget=budget)
                    report['commands'].append(dict(role=row['id'], process=record))
                item = dict(id=row['id'], object=row['object'], depfile=row['depfile'], object_validity='not-produced', input_qualification='not-observed', resource_qualification=record.get('resource_qualification','inconclusive'))
                report['objects'].append(item)
                if record.get('child_started') and record.get('exit_code') == 0:
                    item['object_validity'] = 'fail'
                    item['object_validation'] = common.macho(row['object'], row['id'] == 'libkern/OSData.cpo')
                    item.update(object_validity='pass', object_sha256=digest(row['object']), input_qualification='fail')
                    deps = common.dependencies(row['depfile'],row['cwd'],row['object'])
                    expected = {**plan['inputs'], **{p:v['sha256'] for p,v in plan['projections'].items()}}
                    require(row['source'] in deps, 'Compiler MD omitted exact native source')
                    require(all(p in expected and digest(p) == expected[p] for p in deps), 'Unknown/changed actual native MD input')
                    item.update(input_qualification='pass', depfile_sha256=digest(row['depfile']), dependencies={p:expected[p] for p in deps})
                    item['storage_qualification'] = 'fail'
                    item['storage'] = storage(row['object'],row['id'])
                    item['storage_qualification'] = 'pass'
                verify(common, plan); private_inputs(plan); cancel.check()
                require(record.get('outcome') == 'pass' and record.get('resource_qualification') == 'pass' and item['object_validity'] == 'pass' and item['input_qualification'] == 'pass', 'Stop after failed/deferred native row')
            report['outcome'] = 'pass'
        except BaseException as error:
            report['failure'] = repr(error)
        finally:
            with cancel.cleanup():
                try:
                    if reserved:
                        budget.release()
                except BaseException as error:
                    report.update(outcome='fail', release_error=repr(error))
                if cancel.signals:
                    report.update(outcome='fail', cancellation_signals=cancel.signals)
                report['terminal_sessions'] = [supervise.sample(c['process']['owned_session']) for c in report['commands'] if 'owned_session' in c['process']]
                report['owned_survivors'] = [p for sample in report['terminal_sessions'] for p in sample['owned_processes'] if p['state'] != 'Z']
                if report['owned_survivors']:
                    report['outcome'] = 'fail'
                report['elapsed_seconds'] = time.monotonic()-started
                report['controller_status'] = core.proc_status()
                if out.is_dir():
                    write(out/'evidence.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['plan','execute'])
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--manifest-sha256', required=True)
    p.add_argument('--source-plan', type=Path)
    p.add_argument('--source-plan-sha256')
    p.add_argument('--approval', type=Path)
    p.add_argument('--approval-sha256')
    a = p.parse_args()
    common = module(*PINS[0], 'kernel_log_common')
    plan = derive(common, common.canonical_output_path(a.manifest), a.manifest_sha256)
    if a.mode == 'plan':
        print(json.dumps(plan,indent=2)); return 0
    require(all([a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256]), 'Exact reviewed plan and root approval required')
    report = execute(common,plan,a.source_plan,a.source_plan_sha256,a.approval,a.approval_sha256)
    print(json.dumps(report)); return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
