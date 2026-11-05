#!/usr/bin/env python3
"""Execute reviewed frozen AVF guest compiler recipes in new owned artifact trees."""
import argparse
import ctypes
import datetime
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
PIN = 'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'
TREE = '6a955269a8f4e17d21239f75cef9fbe66cffc56c'
CONFIG = '1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394'
COMPILER = '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'
GIB = 1024**3
GUARDS = {'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
SHARDS = {'osfmk-services': 123, 'osfmk-memory': 125, 'osfmk-machine': 77, 'bsd-filesystems': 90, 'bsd-core': 222, 'bsd-network': 226, 'libkern': 77, 'iokit': 104, 'platform-support': 13, 'security': 23}


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load(path, expected=None, maximum=64*1024**2):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('Missing or oversized JSON input: ' + str(path))
    if expected is not None and sha(path) != expected:
        raise ValueError('Frozen input hash mismatch: ' + str(path))
    with path.open() as stream:
        return json.load(stream)


def actual_controller_memory():
    status = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        if line.startswith(('VmRSS:', 'VmHWM:')):
            key, value = line.split(':', 1); status[key] = int(value.split()[0])*1024
    return {'rss_bytes': status['VmRSS'], 'exec_image_high_water_bytes': status['VmHWM'], 'inherited_ru_maxrss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}


def normalized_index(files, main):
    result = {}
    for name, digest in files.items():
        path = str((main/Path(name)).absolute())
        if path in result and result[path] != digest:
            raise ValueError('Conflicting qualified artifact index aliases')
        result[path] = digest
    return result


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def relative_id(value):
    path = PurePosixPath(value)
    if not isinstance(value, str) or path.is_absolute() or '..' in path.parts or '.' in path.parts or len(path.parts) != 2 or str(path) != value or not re.fullmatch(r'[A-Za-z0-9_+.-]+/[A-Za-z0-9_+.-]+\.(?:o|cpo)', value):
        raise ValueError('Unsafe or noncanonical object ID')
    return path


def validate_graph(rows):
    if not isinstance(rows, list) or len(rows) != 1080:
        raise ValueError('Exact1080-row guest graph required')
    ids = set()
    for row in rows:
        identity = str(relative_id(row['id']))
        if identity in ids or row['component'] != identity.split('/')[0] or row['target'] != identity.split('/')[1]:
            raise ValueError('Duplicate or inconsistent object identity')
        ids.add(identity)
        argv = row['next_owned_compile_argv_template']
        if row['language'] not in ['c', 'c++', 'asm'] or row['status'] != 'genuine_source_and_recipe_bound_not_compiled' or row['execution_requires_new_plan_and_resource_lease'] is not True:
            raise ValueError('Unbound or differently qualified guest recipe')
        if not isinstance(argv, list) or not all(isinstance(a, str) and '\0' not in a for a in argv) or argv.count('-c') != 1:
            raise ValueError('Actual argument-vector compile recipe required')
        for option, expected in [('-o', '@NEXT_OBJECT_DIR@/' + identity), ('-MF', '@NEXT_DEPENDENCY_DIR@/' + identity + '.d')]:
            if argv.count(option) != 1 or argv[argv.index(option)+1] != expected:
                raise ValueError('Undeclared output token or output identity')
        if row['bound_source'] not in argv or argv.count(row['bound_source']) != 1 or not re.fullmatch(r'[0-9a-f]{64}', row['bound_source_sha256']):
            raise ValueError('Genuine source argument is not bound')
        for arg in argv:
            if '@' in arg and arg not in ['@NEXT_OBJECT_DIR@/' + identity, '@NEXT_DEPENDENCY_DIR@/' + identity + '.d']:
                raise ValueError('Unknown placeholder or response file')
            if arg.startswith(('-save-temps', '-fmodules', '-fmodule-', '-fplugin', '-MJ', '-serialize-diagnostics', '--serialize-diagnostics', '-Xclang=-load')) or arg in ['-load', '-plugin', '-add-plugin']:
                raise ValueError('Recipe has an undeclared output/plugin mechanism')
    if sum(row['generated_input'] is True for row in rows) != 55:
        raise ValueError('Genuine generated source count changed')
    return ids


def select(rows, selectors, shard):
    ids = validate_graph(rows)
    if selectors['sha256'] != PIN or set(selectors['shards']) != set(SHARDS):
        raise ValueError('Wrong frozen shard contract')
    seen = set()
    for name, members in selectors['shards'].items():
        if len(members) != SHARDS[name] or len(set(members)) != len(members) or seen.intersection(members):
            raise ValueError('Duplicate, overlapping or incomplete shard')
        seen.update(members)
    if seen != ids or shard not in selectors['shards']:
        raise ValueError('Shard union does not cover the exact graph')
    wanted = set(selectors['shards'][shard])
    return [row for row in rows if row['id'] in wanted]


def expand(row, out):
    roots = {'@NEXT_OBJECT_DIR@': str(out/'objects'), '@NEXT_DEPENDENCY_DIR@': str(out/'dependencies')}
    return [next((a.replace(token, root) for token, root in roots.items() if token in a), a) for a in row['next_owned_compile_argv_template']]


class Digests:
    """Rehash on inode/size/mtime/ctime changes; never materialize binary files."""
    def __init__(self):
        self.cache = {}

    def get(self, path):
        path = Path(path)
        before = path.stat()
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        old = self.cache.get(str(path))
        if old and old[0] == identity:
            return old[1]
        digest = sha(path)
        after = path.stat()
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != identity:
            raise ValueError('Input changed while hashing: ' + str(path))
        self.cache[str(path)] = (identity, digest)
        return digest


def include_roots(row):
    argv = row['next_owned_compile_argv_template']
    cwd = Path(row['cwd'])
    roots = [cwd, Path(row['bound_source']).parent]
    for i, arg in enumerate(argv):
        if arg in ['-I', '-isystem', '-iquote', '-idirafter']:
            roots.append((cwd/argv[i+1]).absolute())
        elif arg.startswith('-I') and len(arg) > 2:
            roots.append((cwd/arg[2:]).absolute())
    return roots


def namespace(rows, index, digests):
    roots = sorted({path.resolve() for row in rows for path in include_roots(row)}, key=lambda p: (len(p.parts), str(p)))
    reduced = []; absent = []
    required = {Path(row[name]).resolve() if name == 'cwd' else Path(row[name]).resolve().parent for row in rows for name in ['cwd', 'bound_source']}
    for root in roots:
        if not root.is_dir():
            if root in required or root.exists():
                raise ValueError('Missing/wrong-kind required source/cwd directory: ' + str(root))
            absent.append(str(root)); continue
        if not any(root.is_relative_to(prior) for prior in reduced):
            reduced.append(root)
    files = {}
    for root in reduced:
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs.sort()
            for name in dirs:
                if (Path(directory)/name).is_symlink():
                    raise ValueError('Unqualified directory symlink in guest namespace')
            for name in sorted(names):
                path = Path(directory)/name
                digest = digests.get(path)
                expected = index.get(str(path)) or index.get(str(path.resolve()))
                if expected != digest:
                    raise ValueError('Unindexed, changed or newly shadowing namespace input: ' + str(path))
                files[str(path)] = digest
    missing = [name for name in index if any(Path(name).is_relative_to(root) for root in reduced) and name not in files]
    if missing:
        raise ValueError('Missing qualified namespace input: '+missing[0])
    result = {'roots': [str(p) for p in reduced], 'absent_search_roots': absent, 'files': files}
    result['sha256'] = canonical(result)
    return result


def bind(args, out):
    if args.manifest_sha256 != PIN:
        raise ValueError('This reviewed executor requires the exact VM008 frozen graph')
    rows = load(args.manifest, PIN)
    selectors = load(args.selectors, args.selectors_sha256)
    if (args.main/selectors['source_manifest']).resolve() != args.manifest.resolve():
        raise ValueError('Selector source manifest identity differs')
    selected = select(rows, selectors, args.shard)
    qualified = load(args.qualification, args.qualification_sha256)
    if (args.main/qualified['next_object_manifest']).resolve() != args.manifest.resolve():
        raise ValueError('Qualified namespace does not bind this graph')
    index_path = args.main/qualified['artifact_index']
    index = normalized_index(load(index_path, qualified['artifact_index_sha256'])['files'], args.main)
    if index.get(str(args.manifest.resolve())) != PIN:
        raise ValueError('Qualified artifact index does not bind frozen graph')
    cache = Digests()
    prepared_path = args.main/qualified['prepared_component']
    if cache.get(prepared_path) != index.get(str(prepared_path)):
        raise ValueError('Qualified prepared component changed')
    prepared = load(prepared_path)
    context = prepared['parent_source']
    for name in ['descriptor', 'composition_manifest']:
        if cache.get(context[name]) != context[name+'_sha256']:
            raise ValueError('Qualified source composition changed: '+name)
    if context['source_tree'] != TREE or context['config_sha256'] != CONFIG:
        raise ValueError('Wrong guest source/config profile')
    compiler = prepared['compiler']
    if compiler['sha256'] != COMPILER or cache.get(compiler['path']) != COMPILER:
        raise ValueError('Genuine builtin-capable compiler changed')
    direct = {str(prepared_path): cache.get(prepared_path), compiler['path']: COMPILER, **{context[name]: context[name+'_sha256'] for name in ['descriptor', 'composition_manifest']}}
    for row in rows:
        if row['next_owned_compile_argv_template'][0] != compiler['path']:
            raise ValueError('Recipe attempts another compiler')
        for path, expected in [(row['bound_source'], row['bound_source_sha256']), (row['configuration'], row['configuration_sha256'])]:
            if cache.get(path) != expected or index.get(path) != expected:
                raise ValueError('Source/configuration no longer matches indexed genuine recipe: ' + path)
            direct[path] = expected
        for arg in row['next_owned_compile_argv_template']:
            if arg.startswith('-fsanitize-ignorelist='):
                path = arg.split('=', 1)[1]
                direct[path] = cache.get(path)
                if index.get(path) != direct[path]:
                    raise ValueError('Changed genuine sanitizer input')
    inputs = namespace(rows, index, cache)
    inputs['files'].update(direct)
    inputs['sha256'] = canonical({k: inputs[k] for k in ['roots', 'absent_search_roots', 'files']})
    provenance = {'manifest': str(args.manifest), 'manifest_sha256': PIN, 'qualification': str(args.qualification), 'qualification_sha256': args.qualification_sha256,
                  'artifact_index': str(index_path), 'artifact_index_sha256': qualified['artifact_index_sha256'], 'selectors': str(args.selectors), 'selectors_sha256': sha(args.selectors),
                  'guest_tree': TREE, 'guest_config_sha256': CONFIG, 'compiler': compiler, 'namespace_sha256': inputs['sha256']}
    plan = {'schema_version': 1, 'provenance': provenance, 'shard': args.shard, 'selected': []}
    for row in selected:
        recipe = canonical(row['next_owned_compile_argv_template'])
        identity = canonical({'provenance': provenance, 'id': row['id'], 'source': row['bound_source_sha256'], 'configuration': row['configuration_sha256'], 'recipe': recipe})
        plan['selected'].append({'id': row['id'], 'input_key': identity, 'source': row['bound_source'], 'source_sha256': row['bound_source_sha256'], 'configuration': row['configuration'], 'configuration_sha256': row['configuration_sha256'], 'recipe_sha256': recipe, 'argv': expand(row, out), 'cwd': row['cwd']})
    write(out/'input-bindings.json', inputs)
    write(out/'execution-plan.json', plan)
    return plan, inputs, cache


def make_tokens(text):
    tokens, token = [], []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 1
            if i == len(text):
                raise ValueError('Dangling dependency escape')
            token.append(text[i])
        elif c == '$' and i+1 < len(text) and text[i+1] == '$':
            token.append('$'); i += 1
        elif c == '#':
            break
        elif c.isspace():
            if token:
                tokens.append(''.join(token)); token = []
        else:
            token.append(c)
        i += 1
    if token:
        tokens.append(''.join(token))
    return tokens


def dependencies(path, cwd, object_path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 16*1024**2:
        raise ValueError('Missing or oversized actual compiler dependency file')
    first = re.sub(r'\\\r?\n', '', path.read_text()).splitlines()[0]
    separator = None
    escaped = False
    for i, c in enumerate(first):
        if c == ':' and not escaped:
            separator = i; break
        escaped = c == '\\' and not escaped
    if separator is None:
        raise ValueError('Malformed compiler dependency rule')
    target = [(Path(cwd)/name).resolve() for name in make_tokens(first[:separator])]
    if target != [Path(object_path).resolve()]:
        raise ValueError('Actual dependency target differs from declared output')
    return sorted({str((Path(cwd)/name).resolve()) for name in make_tokens(first[separator+1:])})


def macho(path, require_metadata=False):
    path = Path(path)
    length = path.stat().st_size
    sections = []
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError('Truncated object header')
        magic, cpu, subtype, kind, count, command_bytes, flags, reserved = struct.unpack('<8I', header)
        if (magic, cpu, kind) != (0xfeedfacf, 0x100000c, 1) or command_bytes > length-32 or count > command_bytes//8:
            raise ValueError('Not a bounded real ARM64 Mach-O object')
        cursor = 32
        for unused in range(count):
            stream.seek(cursor); data = stream.read(8)
            cmd, size = struct.unpack('<II', data)
            if size < 8 or size % 8 or cursor+size > 32+command_bytes:
                raise ValueError('Invalid Mach-O load-command extent')
            if cmd == 25:
                stream.seek(cursor); segment = stream.read(72)
                if len(segment) != 72 or size < 72:
                    raise ValueError('Truncated Mach-O segment')
                nsects = struct.unpack_from('<I', segment, 64)[0]
                if nsects > (size-72)//80:
                    raise ValueError('Invalid Mach-O section count')
                for number in range(nsects):
                    stream.seek(cursor+72+number*80); section = stream.read(80)
                    name, seg, address, extent, offset = struct.unpack_from('<16s16sQQI', section)
                    name = name.split(b'\0')[0].decode('ascii'); seg = seg.split(b'\0')[0].decode('ascii')
                    relocation, relocation_count, section_flags = struct.unpack_from('<III', section, 56)
                    if relocation+relocation_count*8 > length:
                        raise ValueError('Section relocation table exceeds genuine object bytes')
                    section_type = section_flags & 255
                    if section_type not in [1, 12, 18] and offset+extent > length:
                        raise ValueError('Section exceeds genuine object bytes')
                    if 'kalloc' in name:
                        if not extent or offset+extent > length or not seg.startswith('__DATA'):
                            raise ValueError('Empty/truncated/misplaced allocator metadata')
                        stream.seek(offset); remaining = extent; digest = hashlib.sha256()
                        while remaining:
                            chunk = stream.read(min(1024**2, remaining))
                            if not chunk:
                                raise ValueError('Truncated allocator metadata')
                            digest.update(chunk); remaining -= len(chunk)
                        sections.append({'segment': seg, 'section': name, 'size': extent, 'sha256': digest.hexdigest()})
            elif cmd == 2:
                if size != 24:
                    raise ValueError('Invalid MachO symbol command')
                stream.seek(cursor+8); symoff, nsyms, stroff, strsize = struct.unpack('<4I', stream.read(16))
                if symoff+nsyms*16 > length or stroff+strsize > length:
                    raise ValueError('Truncated MachO symbols/string table')
            cursor += size
        if cursor != 32+command_bytes or (require_metadata and not sections):
            raise ValueError('Incomplete load commands or required real allocator metadata absent')
    return {'arm64_macho_object': True, 'cpu_subtype': subtype, 'file_size': length, 'allocator_metadata_sections': sections, 'sha256': sha(path)}


def landlock(out):
    """Called in a single-threaded child's pre-exec; parent remains unrestricted."""
    if platform.machine() not in ['x86_64', 'aarch64']:
        raise ValueError('Landlock syscall mapping unsupported on this host')
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = libc.syscall(444, 0, 0, 1)
    if abi < 3:
        raise OSError('Landlock ABI>=3 required; write confinement never degrades')
    class Rules(ctypes.Structure):
        _fields_ = [('fs', ctypes.c_uint64)]
    class Beneath(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed', ctypes.c_uint64), ('parent', ctypes.c_int32)]
    rights = (1 << 1) | sum(1 << bit for bit in range(4, 15))
    rules = Rules(rights)
    fd = libc.syscall(444, ctypes.byref(rules), ctypes.sizeof(rules), 0)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'landlock_create_ruleset')
    parent = os.open(out, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        rule = Beneath(rights, parent)
        if libc.syscall(445, fd, 1, ctypes.byref(rule), 0) < 0:
            raise OSError(ctypes.get_errno(), 'landlock_add_rule')
        if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.syscall(446, fd, 0) < 0:
            raise OSError(ctypes.get_errno(), 'landlock_restrict_self')
    finally:
        os.close(parent); os.close(fd)


def supervisor(main):
    path = main/'tools/build/qemu_host.py'
    expected = load(main/'fixtures/public/avf-kernel-profile/inputs.json')['accepted_readonly_inputs']['tools/build/qemu_host.py']['sha256']
    if sha(path) != expected:
        raise ValueError('Accepted process supervisor changed')
    spec = importlib.util.spec_from_file_location('avf_objects_supervisor', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def stable_memory(supervise, seconds=45):
    start = time.monotonic(); samples = []; consecutive = 0
    while time.monotonic()-start <= seconds:
        sample = supervise.sample(); samples.append(sample)
        consecutive = consecutive+1 if sample['MemAvailable_bytes'] >= 4*GIB else 0
        if consecutive == 3:
            return {'admitted': True, 'samples': samples, 'elapsed_seconds': time.monotonic()-start}
        if seconds-(time.monotonic()-start) < 1:
            break
        time.sleep(1)
    return {'admitted': False, 'samples': samples, 'elapsed_seconds': time.monotonic()-start}


def run_child(argv, cwd, out, label, supervise, timeout=120, admit=True):
    admission = stable_memory(supervise) if admit else {'admitted': True, 'not_compiler': True}
    record = {'argv': [str(a) for a in argv], 'cwd': str(cwd), 'started_at': stamp(), 'timeout_seconds': timeout, 'rss_budget_bytes': 256*1024**2, 'admission': admission}
    if not admission['admitted']:
        record.update(exit_code=None, outcome='resource-deferred', child_started=False)
        return record
    temp = out/'tmp'; temp.mkdir(exist_ok=True)
    home = out/'home'; home.mkdir(exist_ok=True)
    env = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'TMPDIR': str(temp), 'TMP': str(temp), 'TEMP': str(temp), 'LC_ALL': 'C', 'LANG': 'C', **GUARDS}
    record['environment'] = env
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (2*GIB, 2*GIB))
        landlock(out)
    stdout = out/(label+'.stdout.txt'); stderr = out/(label+'.stderr.txt'); started = time.monotonic(); peak = 0
    with stdout.open('xb') as output, stderr.open('xb') as error, (out/(label+'.samples.jsonl')).open('x') as samples:
        proc = subprocess.Popen(record['argv'], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=error, start_new_session=True, preexec_fn=limits)
        record.update(owned_session=proc.pid, child_started=True)
        try:
            while True:
                sample = supervise.sample(proc.pid)
                controller = int(Path('/proc/self/statm').read_text().split()[1])*resource.getpagesize()
                sample['controller_rss_bytes'] = controller
                sample['total_owned_rss_bytes'] = controller+sample['owned_tree_rss_bytes']
                peak = max(peak, sample['total_owned_rss_bytes']); samples.write(json.dumps(sample)+'\n'); samples.flush()
                if peak > 256*1024**2 or time.monotonic()-started > timeout or (admit and sample['MemAvailable_bytes'] < 4*GIB):
                    record['stop_reason'] = 'rss-budget' if peak > 256*1024**2 else 'deadline' if time.monotonic()-started > timeout else 'MemAvailable-floor'
                    supervise.terminate(proc); break
                if proc.poll() is not None:
                    break
                time.sleep(.025)
            record['exit_code'] = proc.wait(timeout=3)
        finally:
            if any(p['state'] != 'Z' for p in supervise.sample(proc.pid)['owned_processes']):
                supervise.terminate(proc)
            after = supervise.sample(proc.pid)
            record.update(after=after, elapsed_seconds=time.monotonic()-started, peak_total_owned_rss_bytes=peak, stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
    if any(p['state'] != 'Z' for p in after['owned_processes']):
        raise RuntimeError('Owned child survived finite cleanup')
    record['outcome'] = 'resource-deferred' if record.get('stop_reason') in ['MemAvailable-floor', 'rss-budget'] else 'timeout' if record.get('stop_reason') else 'pass' if record['exit_code'] == 0 else 'fail'
    return record


def reusable(item, row, inputs, cache):
    if item.get('id') != row['id'] or item.get('source') != row['source'] or item.get('outcome') != 'pass' or item.get('input_key') != row['input_key']:
        raise ValueError('Resume requires exact unchanged successful input key')
    object_path = Path(item['object'])
    if sha(object_path) != item['object_sha256'] or sha(item['dependency_file']) != item['dependency_file_sha256']:
        raise ValueError('Resume object/dependency bytes changed')
    metadata = macho(object_path, row['id'] == 'libkern/OSData.cpo')
    if metadata != item['object_validation']:
        raise ValueError('Resume object/metadata validation changed')
    dep_paths = dependencies(item['dependency_file'], item['cwd'], item.get('dependency_original_target', item['object']))
    if set(dep_paths) != set(item['dependencies']) or str(Path(row['source']).resolve()) not in dep_paths:
        raise ValueError('Resume dependency/source membership differs')
    for path, digest in item['dependencies'].items():
        if inputs['files'].get(path) != digest or cache.get(path) != digest:
            raise ValueError('Resume actual dependency changed')
    return metadata


def approval(args):
    if not args.approval or not args.approval_sha256:
        raise ValueError('Explicit independently reviewed runner/root lease descriptor required')
    data = load(args.approval, args.approval_sha256)
    if data.get('reviewed_executor_sha256') != sha(__file__) or data.get('runner_reviewed') is not True or not data.get('root_lease') or data.get('max_jobs_per_executor') != 1 or data.get('max_total_project_jobs') != 2 or data.get('max_total_project_rss_bytes', 3*GIB) > 2*GIB:
        raise ValueError('Execution approval does not bind reviewed runner and resource lease')
    ledger = load(args.main/'state/lab.json')
    if not any(t['id'] == 'VM-008' and t['status'] == 'done' for t in ledger['tasks']):
        raise ValueError('VM008 namespace is not accepted/done in MAIN')
    return data


def task_shards(task, mode, requested):
    """Literal reservations authorize a shard; tooling scope never grants execution."""
    if requested not in SHARDS or mode not in ['plan', 'execute']:
        raise ValueError('Unknown shard or execution mode')
    paths = set(task.get('paths', []))
    allowed = {name for name in SHARDS if {
        'fixtures/public/avf-object-shards/'+name,
        'docs/procedures/avf-object-shards/'+name,
    }.issubset(paths)}
    tooling = task['id'] == 'VM-009' and paths == {
        'tools/build/avf_kernel_objects.py',
        'fixtures/public/avf-kernel-objects',
        'docs/procedures/avf-kernel-objects',
    }
    if task['id'] == 'VM-009':
        if mode != 'plan' or not tooling:
            raise ValueError('VM009 tooling scope authorizes source-only plans, never shard compilation')
        return {'authorized_shards': [], 'source_only_tooling_exception': True}
    if requested not in allowed:
        raise ValueError('Requested shard is not reserved by both literal task fixture/procedure paths')
    return {'authorized_shards': sorted(allowed), 'source_only_tooling_exception': False}


def canonical_output_path(value):
    path = Path(value)
    if '..' in path.parts:
        raise ValueError('Parent traversal is forbidden in owned output/worktree paths')
    absolute = path.absolute()
    for ancestor in [absolute, *absolute.parents]:
        if ancestor.is_symlink():
            raise ValueError('Output/worktree ancestry contains a symlink')
    resolved = absolute.resolve(strict=False)
    if resolved != absolute:
        raise ValueError('Owned output/worktree path is not canonical')
    return resolved


def owned_out(args):
    ledger = load(args.main/'state/lab.json')
    tasks = [t for t in ledger['tasks'] if t['id'] == args.task and t.get('owner') == args.owner and t['status'] == 'in_progress']
    experiments = [e for e in ledger['experiments'] if e['id'] == args.experiment and e['task'] == args.task and e['owner'] == args.owner and e['status'] == 'planned']
    if len(tasks) != 1 or len(experiments) != 1 or not tasks[0].get('worktree'):
        raise ValueError('Original active owner and pre-registered MAIN experiment required')
    task = tasks[0]
    authorization = task_shards(task, args.mode, args.shard)
    relative = PurePosixPath(task['worktree'])
    if relative.is_absolute() or '..' in relative.parts or len(relative.parts) < 2 or relative.parts[0] != 'worktrees' or str(relative) != task['worktree']:
        raise ValueError('Ledger worktree must be a canonical relative child of MAIN/worktrees')
    workspace = canonical_output_path(args.main/task['worktree'])
    worktrees = canonical_output_path(args.main/'worktrees')
    if not workspace.is_dir() or not workspace.is_relative_to(worktrees) or workspace == worktrees:
        raise ValueError('Original owner worktree is missing or outside MAIN/worktrees')
    allowed = canonical_output_path(workspace/'artifacts')
    out = canonical_output_path(args.out)
    if not out.is_relative_to(allowed) or out == allowed:
        raise ValueError('New output must be a canonical child of original owner worktree artifacts')
    if out.exists():
        raise ValueError('Existing output directory is never reused or overwritten')
    args.ownership_binding = dict(authorization, task=task['id'], owner=task['owner'], mode=args.mode,
                                  requested_shard=args.shard, worktree=str(workspace), artifact_root=str(allowed),
                                  output=str(out), literal_task_paths=list(task['paths']))
    out.mkdir(parents=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['plan', 'execute'], default='plan')
    parser.add_argument('--main', type=Path, required=True)
    for name in ['manifest', 'qualification', 'selectors']:
        parser.add_argument('--'+name, type=Path, required=True)
        parser.add_argument('--'+name+'-sha256', required=True)
    for name in ['shard', 'owner', 'task', 'experiment']:
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--resume-sha256')
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--approval-sha256')
    args = parser.parse_args(); args.main = args.main.resolve()
    out = owned_out(args)
    shutil.copyfile(__file__, out/'executor.py')
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail', 'recorded_at': stamp(), 'argv': [sys.executable, *sys.argv], 'summary': 'Guest object executor did not complete selected validation', 'executor_sha256': sha(__file__), 'ownership_binding': args.ownership_binding, 'commands': [], 'objects': [], 'compiler_started': False, 'full_kernel_build_or_link': False, 'guest_executed': False, 'device_executed': False, 'sdk_qualified': False, 'private_apple_abi_qualified': False}
    try:
        if args.mode == 'execute':
            report['execution_approval'] = approval(args)
        plan, inputs, cache = bind(args, out)
        report.update(provenance=plan['provenance'], shard=args.shard, selected_ids=[r['id'] for r in plan['selected']], input_bindings=str(out/'input-bindings.json'), input_bindings_sha256=sha(out/'input-bindings.json'))
        if args.mode == 'plan':
            report.update(outcome='pass', summary='Frozen genuine guest graph/shard/source/config/tool/header namespace validated; compiler not started, no object/kernel/guest claim')
        else:
            prior = {}
            if args.resume:
                if not args.resume_sha256:
                    raise ValueError('Explicit immutable resume capsule SHA required')
                previous = load(args.resume, args.resume_sha256)
                if previous['executor_sha256'] != report['executor_sha256']:
                    raise ValueError('Resume runner implementation changed')
                prior = {r['id']: r for r in previous['objects'] if r['outcome'] == 'pass'}
                report['resume'] = {'path': str(args.resume), 'sha256': args.resume_sha256}
            supervise = supervisor(args.main)
            for row in plan['selected']:
                identity = row['id']; output = out/'objects'/identity; dep = out/'dependencies'/(identity+'.d')
                output.parent.mkdir(parents=True, exist_ok=True); dep.parent.mkdir(parents=True, exist_ok=True)
                item = {'id': identity, 'input_key': row['input_key'], 'cwd': row['cwd'], 'outcome': 'fail', 'source': row['source'], 'source_sha256': row['source_sha256']}
                try:
                    if identity in prior:
                        old = load(prior[identity]['record'], prior[identity]['record_sha256'])
                        reusable(old, row, inputs, cache)
                        shutil.copyfile(old['object'], output); shutil.copyfile(old['dependency_file'], dep)
                        item.update(old, object=str(output), dependency_file=str(dep), dependency_original_target=old.get('dependency_original_target', old['object']), reused_from={'record': prior[identity]['record'], 'record_sha256': prior[identity]['record_sha256']})
                    else:
                        result = run_child(row['argv'], row['cwd'], out, identity.replace('/', '_'), supervise)
                        report['commands'].append(result); report['compiler_started'] |= result.get('child_started', False)
                        item['command'] = result
                        if result['outcome'] == 'pass':
                            info = macho(output, identity == 'libkern/OSData.cpo')
                            deps = dependencies(dep, row['cwd'], output)
                            if str(Path(row['source']).resolve()) not in deps:
                                raise ValueError('Actual compiler dependencies omit selected source')
                            actual = {}
                            for path in deps:
                                digest = cache.get(path)
                                if inputs['files'].get(path) != digest:
                                    raise ValueError('Compiler consumed changed/unbound input: ' + path)
                                actual[path] = digest
                            item.update(outcome='pass', object=str(output), object_sha256=sha(output), dependency_file=str(dep), dependency_file_sha256=sha(dep), dependencies=actual, object_validation=info)
                        else:
                            item['outcome'] = result['outcome']
                except Exception as error:
                    item.update(outcome='fail', validation_error=repr(error))
                if item['outcome'] != 'pass':
                    item['partial_artifacts'] = {str(p): sha(p) for p in [output, dep] if p.is_file()}
                record_path = out/(identity.replace('/', '_')+'.object.json'); write(record_path, item)
                report['objects'].append({'id': identity, 'outcome': item['outcome'], 'record': str(record_path), 'record_sha256': sha(record_path)})
                write(out/'progress-next.json', report)
                os.replace(out/'progress-next.json', out/'progress.json')
                if item['outcome'] in ['resource-deferred', 'timeout']:
                    break
                gc.collect()
            # Close the namespace against changed or newly shadowing files, not
            # merely the dependency files of objects that happened to pass.
            rows = load(args.manifest, PIN)
            qualified = load(args.qualification, args.qualification_sha256)
            index = normalized_index(load(args.main/qualified['artifact_index'], qualified['artifact_index_sha256'])['files'], args.main)
            after = namespace(rows, index, cache)
            for path, digest in inputs['files'].items():
                if cache.get(path) != digest:
                    raise ValueError('Input changed during selected execution: ' + path)
            if after['roots'] != inputs['roots'] or after['absent_search_roots'] != inputs['absent_search_roots'] or any(inputs['files'].get(p) != d for p, d in after['files'].items()):
                raise ValueError('Guest namespace changed during compilation')
            report['outcome'] = 'pass' if len(report['objects']) == len(plan['selected']) and all(x['outcome'] == 'pass' for x in report['objects']) else 'fail'
            report['summary'] = 'Actual selected guest object outcomes retained; no full kernel/link/guest/SDK/private ABI claim'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['controller_memory'] = actual_controller_memory()
        report['controller_peak_rss_bytes'] = report['controller_memory']['exec_image_high_water_bytes']
        if report['controller_peak_rss_bytes'] > 256*1024**2:
            report.update(outcome='fail', controller_resource_error='Controller exceeded256MiB; not resource-qualified')
        report['artifact_hashes'] = {str(p): sha(p) for p in out.rglob('*') if p.is_file()}
        report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']
        write(out/'evidence.json', report)
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'shard', 'compiler_started', 'controller_peak_rss_bytes']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
