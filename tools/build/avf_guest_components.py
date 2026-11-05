#!/usr/bin/env python3
"""Admit the two frozen genuine guest component units; no alternate process engine."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT/'fixtures/public/avf-guest-components/policy.json'
POLICY_SHA256 = '04105fefc5bf4f903543f42018d5dd9cc6b485b315aa7bf0a5446a4248ae4136'
GIB = 1024**3


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def load(path, expected=None):
    path = Path(path)
    if path.stat().st_size > 64*1024**2 or (expected and sha(path) != expected):
        raise ValueError('Changed or oversized frozen JSON: '+str(path))
    return json.loads(path.read_text())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')


def module(path, expected, name):
    if sha(path) != expected:
        raise ValueError('Changed pinned Python boundary: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def canonical_path(value):
    path = Path(value).absolute()
    if '..' in path.parts or path != path.resolve():
        raise ValueError('Output must have canonical ancestry without parent traversal')
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError('Symlink ancestry forbidden for output/worktree')
    return path


def owner_authority(ledger, component, args, out):
    """Original component identity and literal reservations, before any mkdir."""
    tasks = [t for t in ledger['tasks'] if t['id'] == component['task']]
    exps = [e for e in ledger['experiments'] if e['id'] == args.experiment]
    if len(tasks) != 1 or len(exps) != 1:
        raise ValueError('One original task and registered experiment required')
    task, exp = tasks[0], exps[0]
    if args.task != component['task'] or args.owner != component['owner'] or task.get('owner') != args.owner or task['status'] != 'in_progress':
        raise ValueError('Original component owner and active component task required')
    if any(exp.get(k) != v for k,v in [('task', args.task), ('owner', args.owner), ('status', 'planned')]):
        raise ValueError('Original planned component experiment required')
    if task.get('worktree') != component['worktree'] or not {'tools/build/'+component['scope'].replace('-', '_')+'.py', 'fixtures/public/'+component['scope'], 'docs/procedures/'+component['scope']}.issubset(set(task['paths'])):
        raise ValueError('Component worktree/literal reservations differ')
    workspace = canonical_path(args.main/component['worktree'])
    if not workspace.is_dir() or not workspace.is_relative_to(args.main/'worktrees'):
        raise ValueError('Missing original owned worktree')
    output = canonical_path(out)
    allowed = [workspace/'artifacts'/component['scope'], workspace/'docs/procedures'/component['scope']]
    if not any(output.is_relative_to(root) and output != root for root in allowed) or output.exists():
        raise ValueError('Fresh original component output scope required')
    return {'task': task['id'], 'owner': task['owner'], 'experiment': exp['id'], 'worktree': str(workspace), 'literal_paths': task['paths'], 'output': str(output)}


def validate_commands(kind, unit, source, out):
    """Compare every argument to the original full recipe before expansion."""
    commands = unit['commands']
    rows = source['recipes'] if kind == 'firehose' else source['translation_units']
    token = '@OWNED_OUTPUT@' if kind == 'firehose' else '@OWNED_OUT@'
    if len(commands) != 4 or len(rows) != 3 or unit['command_count'] != 4:
        raise ValueError('Exactly three genuine compiles then one archive required')
    expected_objects = []; result = []
    for row, command in zip(rows, commands[:3]):
        template = row['argv_template']; argv = command['argv']
        if any(a.startswith('@') and token not in a for a in template):
            raise ValueError('Response or unknown token forbidden')
        if template.count('-o') != 1 or template.count('-MF') != 1:
            raise ValueError('One declared object and dependency output required')
        positions = [template.index('-o')+1, template.index('-MF')+1]
        for i,a in enumerate(template):
            if token in a and (i not in positions or not a.startswith(token+'/') or a.count(token) != 1):
                raise ValueError('Only declared -o/-MF output substitutions permitted')
        expected = [a.replace(token, str(out)) for a in template]
        if argv != expected:
            raise ValueError('Full frozen argv changed, including option order')
        object_path, depfile = [Path(expected[i]) for i in positions]
        if any(p.parent != out or p.name in ['', '.', '..'] for p in [object_path, depfile]) or object_path.suffix != '.o' or depfile.suffix != '.d':
            raise ValueError('Declared output escapes exact fresh root')
        source_path = row['source']['path'] if kind == 'firehose' else row['source']
        expected_cwd = row['cwd'] if kind == 'firehose' else str(out)
        if command['cwd'] != expected_cwd or argv.count('-c') != 1 or argv.count(source_path) != 1:
            raise ValueError('Frozen source/cwd changed')
        expected_objects.append(str(object_path))
        result.append({'id': command['id'], 'argv': argv, 'cwd': expected_cwd, 'object': str(object_path), 'depfile': str(depfile), 'source': source_path,
                       'source_sha256': row['source']['sha256'] if kind == 'firehose' else row['source_sha256'], 'template_sha256': canonical(template), 'argv_sha256': canonical(argv)})
    archive = commands[3]; argv = archive['argv']
    members = expected_objects[:1] if kind == 'firehose' else expected_objects
    if len(argv) != 7 or argv[1:4] != ['-static', '-csD', '-filelist'] or argv[5] != '-o' or archive['cwd'] != str(out):
        raise ValueError('Exact source-qualified archive command required')
    archive_path = out/('libfirehose_kernel.a' if kind == 'firehose' else 'libpthread_kext.a')
    if argv[6] != str(archive_path) or Path(argv[4]).read_text().splitlines() != members:
        raise ValueError('Wrong archive output/filelist/member order, probes or foreign objects')
    result.append({'id': archive['id'], 'argv': argv, 'cwd': str(out), 'archive': str(archive_path), 'members': members, 'filelist': argv[4], 'filelist_sha256': sha(argv[4]), 'argv_sha256': canonical(argv)})
    return result


def pinned(policy, main, key):
    record = policy['pins'][key]; path = main/record['path']
    if sha(path) != record['sha256']:
        raise ValueError('Changed frozen '+key)
    return path


def prepare(main, kind):
    policy = load(POLICY, POLICY_SHA256)
    helper = module(pinned(policy, main, 'helper'), policy['pins']['helper']['sha256'], 'component_frozen_helper')
    unit = load(pinned(policy, main, kind+'_unit'))
    source = load(pinned(policy, main, kind+'_source'))
    producer = module(pinned(policy, main, kind+'_producer'), policy['pins'][kind+'_producer']['sha256'], 'component_'+kind)
    if kind == 'pthread':
        pinned(policy, main, 'pthread_freeze'); producer.validate_plan(source)
    else:
        graph = load(pinned(policy, main, 'graph'))
        original = next(r for r in graph if r['id'] == 'bsd/subr_log.o')
        producer.validate_guest_row(original, main, Path(original['next_owned_compile_argv_template'][0]))
    out = canonical_path(unit['owned_output_directory'] if kind == 'firehose' else unit['output'])
    commands = validate_commands(kind, unit, source, out)
    if commands[0]['argv'][0] != unit['compiler']['path'] or sha(commands[0]['argv'][0]) != policy['compiler_sha256'] or sha(commands[-1]['argv'][0]) != policy['archiver_sha256']:
        raise ValueError('Pinned real compiler/archiver changed')
    for key in ['contract', 'review', 'qualification', 'graph', 'resource', 'compiler_descriptor', 'archiver_descriptor', 'supervisor']:
        pinned(policy, main, key)
    index = helper.normalized_index(load(pinned(policy, main, 'index'))['files'], main)
    review = load(pinned(policy, main, 'source_review'))
    index.update(review['bindings'])
    supplement = load(pinned(policy, main, kind+'_supplement'))
    if kind == 'pthread':
        source_root = main/policy['components'][kind]['worktree']/'artifacts/avf-guest-pthread/prepare-2/source/pthread'
        index.update({str(source_root/r['path']):r['prepared_sha256'] for r in supplement})
        index.update(unit['compile_resources']['public_supplements'])
    else:
        def records(value):
            if isinstance(value, dict):
                if 'path' in value and 'sha256' in value and isinstance(value['path'], str):
                    index[value['path']] = value['sha256']
                for child in value.values(): records(child)
            elif isinstance(value, list):
                for child in value: records(child)
        records(supplement)
        index.update(load(pinned(policy, main, 'firehose_namespace'))['files'])
    return policy, helper, unit, commands, index, out


def snapshot(commands, index, helper, out, cache):
    """Qualified real search namespace; owned outputs are separately closed below."""
    rows = []
    for c in commands[:3]:
        rows.append({'next_owned_compile_argv_template': c['argv'], 'cwd': c['cwd'], 'bound_source': c['source']})
    roots = set()
    for row in rows:
        for root in helper.include_roots(row):
            if any(p.is_symlink() for p in [root,*root.parents]):raise ValueError('Symlink ancestry in source/search namespace')
            # Pthread's explicitly fresh cwd cannot contain source inputs. Its
            # complete prospective/actual root entries are checked separately.
            if root.resolve() != out:
                roots.add(root)
    proxy_rows = [{'next_owned_compile_argv_template': ['-I', str(p)], 'cwd': str(Path(commands[0]['source']).parent), 'bound_source': commands[0]['source']} for p in sorted(roots)]
    result = helper.namespace(proxy_rows, index, cache)
    for c in commands[:3]:
        for name in [c['source'], *[a.split('=',1)[1] for a in c['argv'] if a.startswith('-fsanitize-ignorelist=')]]:
            if index.get(name) != cache.get(name):
                raise ValueError('Changed direct source/ignorelist: '+name)
            result['files'][name] = index[name]
        for i,a in enumerate(c['argv']):
            if a in ['-include', '-imacros']:
                include = Path(c['argv'][i+1])
                search = [include] if include.is_absolute() else [root/include for root in helper.include_roots({'next_owned_compile_argv_template':c['argv'],'cwd':c['cwd'],'bound_source':c['source']})]
                candidates = {str(path.resolve()) for path in search if path.is_file()}
                if not candidates:raise ValueError('Unresolved declared forced include')
                for name in candidates:
                    if index.get(name) != cache.get(name):raise ValueError('Changed forced include candidate')
                    result['files'][name] = index[name]
    result['identities']={}
    for name in result['files']:
        if Path(name).is_symlink():raise ValueError('Unqualified file symlink in source namespace')
        st=Path(name).stat();identity=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        if cache.cache[name][0]!=identity:raise ValueError('Input identity changed during namespace snapshot')
        result['identities'][name]=list(identity)
    result['sha256'] = canonical({k:result[k] for k in ['roots','absent_search_roots','files','identities']})
    return result


def unchanged_namespace(actual,expected):
    if actual!=expected:raise ValueError('Source namespace/content/file identity changed')


def accepted_outputs(accepted,cache):
    for name,item in accepted.items():
        if sha(name)!=item['sha256'] or sha(item['depfile'])!=item['depfile_sha256']:raise ValueError('Previously accepted current output changed')
        for dependency,digest in item['dependencies'].items():
            if cache.get(dependency)!=digest:raise ValueError('Previously accepted dependency changed')


def output_entries(out, commands, completed):
    allowed = {'tmp','home','executor.py','execution-plan.json','input-bindings.json','evidence.json'}
    for number in range(completed+1):
        for suffix in ['.stdout.txt','.stderr.txt','.samples.jsonl']:
            allowed.add('command-'+str(number)+suffix); allowed.add('loader-'+str(number)+suffix)
    for c in commands[:min(completed+1,3)]:
        allowed.update([Path(c['object']).name,Path(c['depfile']).name])
    if completed >= 3: allowed.add(Path(commands[-1]['archive']).name)
    for entry in out.iterdir():
        if entry.name not in allowed or entry.is_symlink() or (entry.is_dir() and entry.name not in ['tmp','home']):
            raise ValueError('Unexpected/shadowing owned cwd entry: '+str(entry))


def elf(path):
    """Read bounded ELF64 dynamic tables, never load the frontend into memory."""
    with Path(path).open('rb') as f:
        header = f.read(64)
        if len(header) != 64 or header[:6] != b'\x7fELF\x02\x01': raise ValueError('Expected little-endian ELF64 host tool')
        phoff = struct.unpack_from('<Q',header,32)[0]; entsize,count = struct.unpack_from('<HH',header,54)
        if entsize != 56 or count > 256: raise ValueError('Invalid ELF program table')
        f.seek(phoff); ph = [struct.unpack('<II6Q', f.read(56)) for _ in range(count)]
        interp = None; entries = []
        for t,flags,offset,vaddr,paddr,filesz,memsz,align in ph:
            if t == 3:
                if filesz > 4096: raise ValueError('Oversized ELF interpreter')
                f.seek(offset); interp=f.read(filesz).rstrip(b'\0').decode()
            if t == 2:
                if filesz > 1024**2 or filesz%16: raise ValueError('Invalid ELF dynamic extent')
                f.seek(offset)
                for _ in range(filesz//16):
                    tag,value=struct.unpack('<qQ',f.read(16))
                    if tag == 0:break
                    entries.append((tag,value))
        if any(tag in [0x6ffffefb,0x6ffffefc] for tag,value in entries):raise ValueError('ELF audit/depaudit modules are forbidden')
        strings = dict(entries)
        if 5 not in strings or 10 not in strings or strings[10] > 16*1024**2: raise ValueError('Missing bounded ELF strings')
        address = strings[5]
        segment = next((p for p in ph if p[0] == 1 and p[3] <= address and address+strings[10] <= p[3]+p[5]),None)
        if segment is None: raise ValueError('ELF strings outside file-backed segment')
        f.seek(segment[2]+address-segment[3]); table=f.read(strings[10])
        def text(offset):
            end=table.find(b'\0',offset)
            if offset >= len(table) or end < 0:raise ValueError('Invalid ELF dynamic string')
            return table[offset:end].decode()
        return {'interpreter':interp,'needed':[text(v) for k,v in entries if k == 1], 'runpath':[text(v) for k,v in entries if k in [15,29]]}


def runtime_candidates(unit):
    if 'host_runtime_files' in unit:
        return {Path(r['path']).name:r for r in unit['host_runtime_files']}
    return {Path(r['resolved_path']).name:{'path':r['resolved_path'],'sha256':r['sha256']} for r in unit['ELF_runtime']['host_runtime_candidates'].values()}


def runtime_snapshot(binary, cwd, unit, helper, cache):
    facts = elf(binary); candidates = runtime_candidates(unit)
    files = {}; names = set(facts['needed'])|{'libm.so.6','libstdc++.so.6','libgcc_s.so.1','libc.so.6','ld-linux-x86-64.so.2'}
    policy=load(POLICY,POLICY_SHA256)
    diagnostics=load(ROOT/'fixtures/public/avf-guest-components/loader-diagnostics.json',policy['pins']['loader_diagnostics']['sha256'])
    values=diagnostics['values']
    directories={Path(cwd)}|{Path(v) for k,v in values.items() if k.startswith('path.system_dirs[')}
    elf_files={str(binary):facts}
    for item in candidates.values():
        if cache.get(item['path'])!=item['sha256']:raise ValueError('Changed qualified runtime candidate')
        elf_files[item['path']]=elf(item['path'])
    for path,description in elf_files.items():
        names.update(description['needed'])
        for string in description['runpath']:
            for part in string.split(':'):
                # Preserve the literal spelling as well as loader token expansion.
                expanded=part
                for token,replacement in [('ORIGIN',str(Path(path).parent)),('LIB',values['dl_dst_lib']),('PLATFORM',values['dl_platform'])]:
                    expanded=expanded.replace('${'+token+'}',replacement).replace('$'+token,replacement)
                if '$' in expanded:raise ValueError('Unqualified runtime search token')
                for spelling in [part,expanded]:
                    directories.add(Path(cwd)/spelling if not Path(spelling).is_absolute() else Path(spelling))
    for directory in list(directories):
        for subdir in values['dl_hwcaps_subdirs'].split(':'):
            directories.add(directory/'glibc-hwcaps'/subdir)
    lookup = {}
    for root in sorted(directories,key=str):
        for name in sorted(names):
            logical = root/name
            key=str(logical)
            if logical.exists() or logical.is_symlink():
                real=logical.resolve(strict=True)
                if str(real) not in {r['path'] for r in candidates.values()} or cache.get(real) != next(r['sha256'] for r in candidates.values() if r['path'] == str(real)):
                    raise ValueError('Unqualified runtime search shadow: '+str(logical))
                lookup[key]={'realpath':str(real),'sha256':cache.get(real),'link':os.readlink(logical) if logical.is_symlink() else None}
            else:lookup[key]=None
    for item in candidates.values():
        if cache.get(item['path']) != item['sha256']:raise ValueError('Changed qualified runtime candidate')
        files[item['path']]=item['sha256']
    interpreter=Path(facts['interpreter'] or '/lib64/ld-linux-x86-64.so.2')
    if str(interpreter.resolve(strict=True)) not in files:raise ValueError('Unqualified actual ELF interpreter')
    preload=Path('/etc/ld.so.preload')
    if preload.exists() and preload.read_text().strip():raise ValueError('System loader preload is unqualified')
    preload_state=cache.get(preload) if preload.is_file() else None
    for path in ['/etc/ld.so.cache','/etc/ld.so.conf']:
        p=Path(path)
        if p.is_file():files[path]=cache.get(p)
    return {'elf':facts,'transitive_ELF':elf_files,'lookup':lookup,'candidate_files':files,'interpreter':str(interpreter),'system_preload_sha256':preload_state,'loader_diagnostics_sha256':policy['pins']['loader_diagnostics']['sha256'],'sha256':canonical([elf_files,lookup,files,preload_state])}


def loaded_runtime(text, runtime):
    """Require actual trusted-interpreter --list mapping, not candidate inference."""
    mapped={}
    for line in text.splitlines():
        parts=line.strip().split()
        if not parts:continue
        if parts[0].startswith('linux-vdso.so.'):
            continue
        if '=>' in parts:
            if len(parts)<3 or parts[2]=='not':raise ValueError('Missing runtime library')
            path=Path(parts[2]);logical=parts[0]
        elif parts[0].startswith('/'):
            path=Path(parts[0]);logical=path.name
        else:raise ValueError('Unrecognized actual loader mapping')
        resolved=str(path.resolve(strict=True));expected=runtime['candidate_files'].get(resolved)
        if expected is None or sha(resolved)!=expected:raise ValueError('Unexpected actual loaded dependency')
        mapped[logical]={'path':str(path),'resolved_path':resolved,'sha256':expected}
    if not set(runtime['elf']['needed']).issubset(mapped):raise ValueError('Actual loader omitted declared dependency')
    if not any(v['resolved_path']==str(Path(runtime['interpreter']).resolve()) for v in mapped.values()):raise ValueError('Actual loader interpreter absent')
    return mapped


def object_details(path, helper, metadata=False):
    if Path(path).stat().st_size > 64*1024**2:raise ValueError('Oversized component object')
    info=helper.macho(path,require_metadata=metadata); sections=[]; symbols=[]
    with Path(path).open('rb') as f:
        header=f.read(32); count=struct.unpack_from('<I',header,16)[0]; cursor=32
        for _ in range(count):
            f.seek(cursor);cmd,size=struct.unpack('<II',f.read(8))
            if cmd==25:
                f.seek(cursor+64);number=struct.unpack('<I',f.read(4))[0]
                for n in range(number):
                    f.seek(cursor+72+n*80);s=f.read(80);name,seg,addr,extent,offset=struct.unpack_from('<16s16sQQI',s)
                    name=name.rstrip(b'\0').decode();seg=seg.rstrip(b'\0').decode()
                    sections.append({'name':name,'segment':seg,'address':addr,'size':extent,'offset':offset})
            if cmd==2:
                f.seek(cursor+8);off,n,stroff,strsize=struct.unpack('<4I',f.read(16))
                if strsize>16*1024**2 or n>1024**2:raise ValueError('Oversized component symbol table')
                f.seek(stroff);strings=f.read(strsize)
                f.seek(off)
                for ordinal in range(n):
                    index,kind,sect,desc,value=struct.unpack('<IBBHQ',f.read(16))
                    if index>=len(strings) or strings.find(b'\0',index)<0:raise ValueError('Malformed raw Mach-O symbol name')
                    name=strings[index:strings.find(b'\0',index)].decode()
                    symbols.append({'name':name,'type':kind,'section':sect,'value':value,'external':bool(kind&1),'undefined':kind&14==0})
            cursor+=size
    info.update(sections=sections,symbols=symbols)
    return info


def inspect_object(command, kind, helper):
    info=object_details(command['object'],helper)
    definitions={s['name'] for s in info['symbols'] if s['external'] and not s['undefined'] and not s['type']&224}
    imports={s['name'] for s in info['symbols'] if s['external'] and s['undefined']}
    if kind=='firehose':
        if command['id'].endswith('provider') or command['id'].endswith('provider-layout'):
            if '___firehose_buffer_create' not in definitions:raise ValueError('Genuine provider definition absent')
        if command['id'].endswith('provider-layout') or command['id'].endswith('interface'):
            expected_name='_s24_firehose_provider' if command['id'].endswith('provider-layout') else '_s24_firehose_interface'
            symbol=next((s for s in info['symbols'] if s['name']==expected_name and not s['undefined']),None)
            if not symbol or not 0<symbol['section']<=len(info['sections']):raise ValueError('Missing actual Firehose probe record')
            section=info['sections'][symbol['section']-1];count=9 if command['id'].endswith('provider-layout') else 11
            relative=symbol['value']-section['address']
            if section['name']!='__s24fh' or section['segment']!='__DATA_CONST' or relative<0 or relative+count*8>section['size']:raise ValueError('Wrong/truncated Firehose record section')
            with Path(command['object']).open('rb') as f:f.seek(section['offset']+relative);record=list(struct.unpack('<'+'Q'*count,f.read(count*8)))
            if count==9:
                if record[:3]!=[8,1,8] or record[6:8]!=[24,24] or any(v==0 for v in record):raise ValueError('Wrong target-derived provider layout')
            elif record!=[20180226,24,24,4096,16,4,8,16,16,64,8]:raise ValueError('Wrong actual interface probe values')
            info['probe_record']=record
            if count==11:
                required={'___firehose_buffer_tracepoint_reserve','___firehose_buffer_tracepoint_flush','___firehose_buffer_create','___firehose_merge_updates','___firehose_kernel_configuration_valid','___firehose_allocate','___firehose_critical_region_enter','___firehose_critical_region_leave','___firehose_buffer_push_to_logd'}
                if not required.issubset(imports):raise ValueError('Actual interface function relocations/imports absent')
    else:
        forbidden={'_pthread_kern','_current_uthread'}
        if (definitions|imports)&forbidden:raise ValueError('Pthread namespace remap absent')
        if command['id']=='compile-kern_init' and not {'_pthread_start','_pthread_kext_kern'}.issubset(definitions):raise ValueError('Genuine pthread init/remapped definition absent')
    info.update(definitions=sorted(definitions),imports=sorted(imports))
    return info


def archive_members(path):
    """Bounded BSD/GNU short-name ar reader; reject unsupported name indirection."""
    result=[]
    with Path(path).open('rb') as f:
        if f.read(8)!=b'!<arch>\n':raise ValueError('Not an actual ar archive')
        while True:
            header=f.read(60)
            if not header:break
            if len(header)!=60 or header[58:]!=b'`\n' or not header[48:58].strip().isdigit():raise ValueError('Truncated/invalid ar header')
            size=int(header[48:58]);name=header[:16].decode('ascii').strip();remaining=size
            if size>64*1024**2:raise ValueError('Oversized member')
            if name.startswith('#1/'):
                n=int(name[3:])
                if n>size:raise ValueError('Truncated BSD member name')
                raw=f.read(n)
                if len(raw)!=n:raise ValueError('Truncated BSD member name')
                name=raw.rstrip(b'\0').decode();remaining-=n
            else:name=name.rstrip('/')
            h=hashlib.sha256()
            while remaining:
                block=f.read(min(1024**2,remaining))
                if not block:raise ValueError('Truncated archive member')
                h.update(block);remaining-=len(block)
            if size%2 and len(f.read(1))!=1:raise ValueError('Truncated archive padding')
            if name.startswith('__.SYMDEF'):continue
            if '/' in name or not name:raise ValueError('Unsupported/unsafe archive member name')
            result.append({'name':name,'sha256':h.hexdigest()})
    return result


def inspect_archive(command, accepted):
    expected=[{'name':Path(p).name,'sha256':accepted[p]['sha256']} for p in command['members']]
    for p in command['members']:
        if sha(p)!=accepted[p]['sha256']:raise ValueError('Generated archive input changed after inspection')
    actual=archive_members(command['archive'])
    if actual!=expected:raise ValueError('Archive order/set/member bytes differ from just-validated genuine objects')
    definitions={}
    for path in command['members']:
        for name in accepted[path]['definitions']:
            if name in definitions:raise ValueError('Duplicate external provider definition: '+name)
            definitions[name]=path
    return {'sha256':sha(command['archive']),'members':actual,'definitions':definitions}


def verify_dependencies(command, inputs, helper, cache):
    names=helper.dependencies(command['depfile'],command['cwd'],command['object'])
    if str(Path(command['source']).resolve()) not in names:raise ValueError('Actual source missing from compiler dependency closure')
    result={}
    for name in names:
        if inputs['files'].get(name)!=cache.get(name):raise ValueError('Actual dependency changed/unqualified: '+name)
        result[name]=cache.get(name)
    return result


def success(record):
    if record.get('outcome')!='pass' or record.get('exit_code')!=0 or not record.get('child_started') or any(p['state']!='Z' for p in record.get('after',{}).get('owned_processes',[{'state':'?'}])):
        raise ValueError('Failed/deferred command cannot qualify or continue to archive')


def plan(main,kind):
    policy,helper,unit,commands,index,out=prepare(main,kind)
    cache=helper.Digests();inputs=snapshot(commands,index,helper,out,cache)
    runtime=[runtime_snapshot(Path(c['argv'][0]),Path(c['cwd']),unit,helper,cache) for c in commands]
    return {'schema':'guest-component-execution-v1','resource_profile':'project-budget-v1','component':kind,'task':policy['components'][kind]['task'],
            'owner':policy['components'][kind]['owner'],'output':str(out),'policy_sha256':POLICY_SHA256,'executor_sha256':sha(__file__),
            'unit':policy['pins'][kind+'_unit'],'source_plan':policy['pins'][kind+'_source'],'process_policy':policy['prospective_process'],
            'commands':commands,'inputs_sha256':inputs['sha256'],'runtime':runtime,'qualification':'source-plan-only','compiled':False},inputs


def execute(args):
    policy,helper,unit,commands,index,out=prepare(args.main,args.component)
    if args.out!=out:raise ValueError('Execution output must equal exact original unit output')
    ownership=owner_authority(load(args.main/'state/lab.json'),policy['components'][args.component],args,out)
    process=policy['prospective_process']
    if not process:raise ValueError('Reviewed prospective common budget/process pin is not yet published')
    engine=module(args.main/process['path'],process['sha256'],'component_budget_engine')
    args.shard=args.component
    approval=load(args.approval,args.approval_sha256)
    budget=engine.project_approval(args,approval,executor_path=Path(__file__))
    planned,inputs=plan(args.main,args.component)
    if budget.source_plan!=planned:raise ValueError('Root allocation does not bind the exact current component plan')
    if budget.rss_limit!=256*1024**2:raise ValueError('Component controller+tree remains serial256MiB')
    supervise=engine.supervisor(args.main);cache=helper.Digests();accepted={};records=[];started=time.monotonic();reserved=False
    report={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.now(timezone.utc).isoformat(), 'task':args.task,'ownership':ownership,
            'executor_sha256':sha(__file__),'plan_sha256':canonical(planned),'commands':records,'objects':accepted,'archive':None,
            'full_kernel_qualified':False,'callback_alias_ABI_qualified':False,'native_device_qualified':False,'guest_executed':False}
    try:
        budget.reserve();reserved=True
        # Revalidate original authority after budget wait, still before mkdir.
        owner_authority(load(args.main/'state/lab.json'),policy['components'][args.component],args,out)
        out.mkdir(parents=True,exist_ok=False)
        (out/'executor.py').write_bytes(Path(__file__).read_bytes());write(out/'execution-plan.json',planned);write(out/'input-bindings.json',inputs)
        for number,c in enumerate(commands):
            output_entries(out,commands,number)
            prepare(args.main,args.component)
            before=snapshot(commands,index,helper,out,cache)
            unchanged_namespace(before,inputs)
            accepted_outputs(accepted,cache)
            runtime=runtime_snapshot(Path(c['argv'][0]),Path(c['cwd']),unit,helper,cache)
            if runtime!=planned['runtime'][number]:raise ValueError('Host runtime/search namespace changed')
            # The trusted pinned interpreter lists actual resolution without
            # entering compiler/libtool main. It uses the same process boundary.
            loader=engine.run_child([runtime['interpreter'],'--list',c['argv'][0]],Path(c['cwd']),out,'loader-'+str(number),supervise,timeout=30,admit=True,budget=budget)
            records.append({'role':'loader-resolution','process':loader});success(loader)
            mapping=loaded_runtime((out/('loader-'+str(number)+'.stdout.txt')).read_text(),runtime)
            if runtime_snapshot(Path(c['argv'][0]),Path(c['cwd']),unit,helper,cache)!=runtime:raise ValueError('Runtime changed during loader resolution')
            if number==3:
                if len(accepted)!=3:raise ValueError('All three genuine current compiles required before archive')
                if sha(c['filelist'])!=c['filelist_sha256']:raise ValueError('Archive filelist changed')
                for member in c['members']:
                    if sha(member)!=accepted[member]['sha256']:raise ValueError('Current object changed before archive')
            record=engine.run_child(c['argv'],Path(c['cwd']),out,'command-'+str(number),supervise,timeout=120,admit=True,budget=budget)
            records.append({'role':c['id'],'process':record,'actual_runtime':mapping});success(record)
            output_entries(out,commands,number)
            unchanged_namespace(snapshot(commands,index,helper,out,cache),inputs)
            if runtime_snapshot(Path(c['argv'][0]),Path(c['cwd']),unit,helper,cache)!=runtime:raise ValueError('Runtime changed during command')
            accepted_outputs(accepted,cache)
            if number<3:
                metadata=inspect_object(c,args.component,helper);metadata['dependencies']=verify_dependencies(c,inputs,helper,cache);metadata['depfile_sha256']=sha(c['depfile']);metadata['depfile']=c['depfile'];accepted[c['object']]=metadata
            else:report['archive']=inspect_archive(c,accepted)
        report['outcome']='pass';report['qualification']='three actual component TU objects and exact archive only'
    except BaseException as error:
        report['failure']={'type':type(error).__name__,'message':str(error)}
        raise
    finally:
        try:
            if reserved:budget.release()
        except BaseException as cleanup_error:
            report['cleanup_failure']={'type':type(cleanup_error).__name__,'message':str(cleanup_error)}
            report['outcome']='fail'
            raise
        finally:
            if out.is_dir() and not (out/'evidence.json').exists():
                report.update(elapsed_seconds=time.monotonic()-started,current_image_memory=helper.actual_controller_memory(),inherited_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                write(out/'evidence.json',report)
        report.update(elapsed_seconds=time.monotonic()-started,current_image_memory=helper.actual_controller_memory(),inherited_ru_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['plan','execute'],default='plan');p.add_argument('--main',required=True,type=Path);p.add_argument('--component',required=True,choices=['firehose','pthread']);p.add_argument('--out',required=True,type=Path)
    for name in ['task','owner','experiment']:p.add_argument('--'+name)
    p.add_argument('--approval',type=Path);p.add_argument('--approval-sha256')
    a=p.parse_args();a.main=canonical_path(a.main);a.out=canonical_path(a.out)
    if a.mode=='execute':
        if not all([a.task,a.owner,a.experiment,a.approval,a.approval_sha256]):p.error('Execution requires original task/owner/experiment and exact root approval')
        result=execute(a)
    else:
        # Planning never creates the original component execution cwd/output.
        if all([a.task,a.owner,a.experiment]):
            policy,helper,unit,commands,index,target=prepare(a.main,a.component)
            ledger=load(a.main/'state/lab.json')
            owner_authority(ledger,policy['components'][a.component],a,target)
            owner_authority(ledger,policy['components'][a.component],a,a.out)
        else:
            own=canonical_path(ROOT/'artifacts/avf-guest-components')
            if not a.out.is_relative_to(own) or a.out==own or a.out.exists():raise ValueError('Source plans require a fresh VM036-owned artifact directory')
        result,inputs=plan(a.main,a.component);a.out.mkdir(parents=True,exist_ok=False);write(a.out/'execution-plan.json',result);write(a.out/'input-bindings.json',inputs)
    print(json.dumps({'outcome':result.get('outcome','pass'),'qualification':result['qualification'],'output':str(a.out)}))


if __name__=='__main__':main()
