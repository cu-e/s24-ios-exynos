#!/usr/bin/env python3
"""One image-admitted AVF collector. An absent genuine image refuses before spawn.

An admission is an exact committed allowlist entry binding independent review,
raw source-to-link evidence and actual bytes. Caller-supplied success booleans
cannot create an admission. Host controls and collected text never qualify XNU.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import resource
import signal
import socket
import stat
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'fixtures/public/avf-kernel-boot/inputs.json'
OWNER = 'codex-guest-collector-20261106-eh'
PROTOCOL = 'vm040-paused-cont-v1'
MAX_JSON = 4 << 20
MAX_FDT = 2 << 20
MAX_LOG = 4 << 20
RSS_LIMIT = 512 << 20
DEADLINE = 60
APPEND = 'cpus=1 -v serial=3 -enable_kprintf_spam console_quiet=0 disable-uart-irq=1 avf_exit=1'


class Refused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Refused(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path, offset=0, length=None):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        stream.seek(offset)
        remaining = length
        while remaining is None or remaining:
            block = stream.read(65536 if remaining is None else min(65536, remaining))
            if not block:
                require(remaining in (None, 0), 'Truncated bound extent')
                break
            h.update(block)
            if remaining is not None:
                remaining -= len(block)
    return h.hexdigest()


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key: ' + key)
        result[key] = value
    return result


def decode_json(data):
    def bad_constant(value):
        raise Refused('Nonfinite JSON value: ' + value)
    return json.loads(data, object_pairs_hook=no_duplicates, parse_constant=bad_constant)


def read_json(path, bound=MAX_JSON):
    require(Path(path).stat().st_size <= bound, 'JSON exceeds bound')
    with Path(path).open('rb') as stream:
        data = stream.read(bound + 1)
    require(len(data) <= bound, 'JSON grew beyond bound')
    return decode_json(data)


def inside(root, relative, *, exists=True):
    root = Path(root).resolve()
    rel = Path(relative)
    require(isinstance(relative, str) and not rel.is_absolute() and '..' not in rel.parts,
            'Expected an owned relative path')
    path = root / rel
    require(path.absolute() == path.resolve() and path.resolve().is_relative_to(root),
            'Symlink or escaping path rejected')
    if exists:
        require(path.is_file() and stat.S_ISREG(path.stat().st_mode), 'Regular input file required')
    return path


def binding(main, row, *, maximum=2 << 30):
    require(isinstance(row, dict) and set(row) == {'path', 'sha256', 'size'}, 'Binding shape mismatch')
    require(type(row['size']) is int and 0 <= row['size'] <= maximum, 'Binding size outside policy')
    require(isinstance(row['sha256'], str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Invalid SHA256')
    path = inside(main, row['path'])
    require(path.stat().st_size == row['size'] and digest(path) == row['sha256'],
            'Changed bound bytes: ' + row['path'])
    return path


def output_dir(path):
    path = Path(path).absolute()
    base = (ROOT / 'artifacts/avf-kernel-boot').resolve()
    require(path == path.resolve() and path.parent == base and
            re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}', path.name),
            'Run must be a canonical direct child of collector artifacts')
    require(not path.exists(), 'Run output must be fresh')
    return path


def helper(main, pins, name):
    path = binding(main, pins['helpers'][name], maximum=1 << 20)
    spec = importlib.util.spec_from_file_location('vm040_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admitted_descriptor(main, pins, image_id):
    matches = [row for row in pins['image_admissions'] if row['id'] == image_id]
    require(len(matches) == 1,
            'No admitted genuine kernel image exists for this collector; execution refused before launch')
    entry = matches[0]
    descriptor_path = binding(main, entry['descriptor'])
    review = read_json(binding(main, entry['independent_review']))
    receipt = read_json(binding(main, entry['root_acceptance']))
    require(review['outcome'] == 'pass' and review['descriptor_sha256'] == entry['descriptor']['sha256']
            and receipt['accepted_review_sha256'] == entry['independent_review']['sha256']
            and receipt['descriptor_sha256'] == entry['descriptor']['sha256'],
            'Independent image admission chain mismatch')
    data = read_json(descriptor_path)
    require(data['protocol'] == PROTOCOL and data['profile'] == 'ARM64/DEVELOPMENT/BCM2837',
            'Unreviewed image protocol or profile')
    return entry, data


def fdt(data):
    """Strict bounded Linux input FDT parser, never the later Apple serialized DT."""
    require(40 <= len(data) <= MAX_FDT, 'FDT byte bound')
    magic, total, start, strings_start, reserve, version, compat, _, strings_size, size = struct.unpack_from('>10I', data)
    require(magic == 0xd00dfeed and total == len(data) and version == 17 and compat <= 17,
            'FDT header identity/length/version')
    require(40 <= start <= total and size <= total - start and 40 <= strings_start <= total
            and strings_size <= total - strings_start and reserve % 8 == 0 and 40 <= reserve < total,
            'FDT block bounds')
    require(start + size <= strings_start or strings_start + strings_size <= start, 'FDT block overlap')
    pos = reserve
    for _ in range(1024):
        require(pos + 16 <= total, 'FDT reservation bounds')
        address, length = struct.unpack_from('>QQ', data, pos); pos += 16
        if (address, length) == (0, 0):
            break
    else:
        raise Refused('FDT reservation budget')
    require(pos <= start or reserve >= start + size, 'FDT reservations overlap structure')
    strings = data[strings_start:strings_start + strings_size]
    offset, stack, props, ended, nodes = start, [], {}, False, set()
    for _ in range(65536):
        require(offset + 4 <= start + size, 'FDT token bounds')
        token = struct.unpack_from('>I', data, offset)[0]; offset += 4
        if token == 1:
            end = data.find(b'\0', offset, start + size)
            require(end >= 0 and end - offset <= 255 and len(stack) < 32, 'FDT node bounds/depth')
            name = data[offset:end].decode('ascii')
            require('/' not in name and (stack or name == ''), 'FDT node name')
            stack.append(name); offset = (end + 4) & ~3
            node = '/' + '/'.join(stack[1:])
            require(node not in nodes, 'Duplicate FDT node')
            nodes.add(node)
        elif token == 2:
            require(bool(stack), 'FDT stack underflow')
            stack.pop()
        elif token == 3:
            require(bool(stack) and offset + 8 <= start + size, 'FDT property header')
            length, nameoff = struct.unpack_from('>II', data, offset); offset += 8
            require(length <= start + size - offset and nameoff < len(strings), 'FDT property bounds')
            end = strings.find(b'\0', nameoff)
            require(end >= 0, 'FDT property name termination')
            key = ('/' + '/'.join(stack[1:]), strings[nameoff:end].decode('ascii'))
            require(key not in props, 'Duplicate FDT property')
            props[key] = data[offset:offset + length]; offset += (length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            require(not stack and offset == start + size, 'FDT unclosed/trailing structure')
            ended = True
            break
        else:
            raise Refused('Unknown FDT token')
    require(ended, 'FDT end absent')
    return props


def fdt_contract(props, layout, package):
    require(props[('/', '#address-cells')] == struct.pack('>I', 2) and
            props[('/', '#size-cells')] == struct.pack('>I', 2), 'FDT root cell widths')
    memory = [node for (node, name), value in props.items()
              if node.count('/') == 1 and name == 'device_type' and value == b'memory\0']
    require(len(memory) == 1 and props.get((memory[0], 'reg')) ==
            struct.pack('>QQ', 0x40000000, 256 << 20), 'FDT memory device_type or RAM span differs')
    require(props[('/psci', 'method')] == b'hvc\0', 'FDT PSCI must be HVC')
    require(props[('/pl011@9000000', 'reg')] == struct.pack('>QQ', 0x09000000, 0x1000), 'FDT PL011 mapping')
    def compatible(node, expected):
        raw = props[(node, 'compatible')]
        return raw.endswith(b'\0') and expected in raw[:-1].split(b'\0')
    require(compatible('/pl011@9000000', b'arm,pl011'), 'FDT PL011 compatible token')
    require(compatible('/intc@8000000', b'arm,gic-v3'), 'FDT GICv3 compatible token')
    require(struct.unpack('>4Q', props[('/intc@8000000', 'reg')]) ==
            (0x08000000, 0x10000, 0x080a0000, 0xf60000), 'FDT GIC register spans differ from pinned QEMU')
    timer = struct.unpack('>12I', props[('/timer', 'interrupts')])
    require(timer[6] == 1 and timer[7] == 11, 'FDT virtual timer must be PPI27')
    require(props[('/chosen', 'bootargs')] == APPEND.encode() + b'\0', 'FDT append differs')
    for key, expected in [('linux,initrd-start', layout['payload_base']),
                          ('linux,initrd-end', layout['payload_base'] + package['size'])]:
        value = props[('/chosen', key)]
        require(len(value) in (4, 8) and int.from_bytes(value, 'big') == expected, 'FDT initrd extent mismatch')
    return {'kind': 'Linux-input-FDT', 'psci': 'hvc', 'virtual_timer_intid': 27,
            'ram_base': 0x40000000, 'ram_size': 256 << 20, 'append': APPEND}


def embedded_identity(memory, payload, kernel, ramdisk):
    package = memory.payload(payload)
    require(set(package['entries']) == {'kernel', 'ramdisk', 'cmdline'}, 'Unsupported XNUP entries')
    for name, path in [('kernel', kernel), ('ramdisk', ramdisk)]:
        entry = package['entries'][name]
        require(entry['size'] == path.stat().st_size and
                digest(payload, entry['offset'], entry['size']) == digest(path),
                'XNUP embedded ' + name + ' differs from admitted bytes')
    return package


def combined_arguments(value):
    require(isinstance(value, str) and value.isascii() and '\0' not in value
            and len(value) < 608, 'Bounded ASCII combined boot args required')
    expected = {'debug': '0x8', 'serial': '3', 'cpus': '1', 'rd': 'md0', 'console_quiet': '0',
                'disable-uart-irq': '1', 'avf_exit': '1', '-enable_kprintf_spam': '', '-v': ''}
    observed = {}
    for token in value.split():
        key, _, val = token.partition('=')
        require(key in expected and val == expected[key], 'Unsupported/conflicting final boot argument: ' + token)
        observed[key] = val
    require(observed == expected, 'Complete final combined argument vector is required')
    return value.split()


def object_lineage(main, lineage, expected, stop):
    rows = lineage['objects']
    require(len(expected) == len(rows) == 1080 and
            [r['id'] for r in rows] == [r['id'] for r in expected]
            and len({r['id'] for r in rows}) == 1080, 'Complete ordered 1080-object lineage required')
    for row, original in zip(rows, expected):
        stop.check()
        source = binding(main, row['source'])
        output = binding(main, row['producer_object'])
        receipt = read_json(binding(main, row['compile_receipt']))
        require(source == Path(original['source']) and row['source']['sha256'] == original['source_sha256']
                and receipt['id'] == row['id'] and receipt['outcome'] == 'pass'
                and receipt['source'] == str(source) and receipt['source_sha256'] == row['source']['sha256']
                and receipt['object'] == str(output) and receipt['object_sha256'] == row['producer_object']['sha256']
                and receipt['command']['exit_code'] == 0, 'Raw compiled object/source/receipt mismatch')
        dep = Path(receipt['dependency_file'])
        require(dep.resolve().is_relative_to(main.resolve()) and digest(dep) == receipt['dependency_file_sha256'],
                'Compiled dependency-file binding mismatch')


def prepare(main, image_id, run_dir, stop=None):
    stop = stop or Stop()
    stop.check()
    pins = read_json(FIXTURE)
    entry, descriptor = admitted_descriptor(main, pins, image_id)
    paths = {}
    for name, row in descriptor['files'].items():
        stop.check(); paths[name] = binding(main, row)
    required = {'kernel', 'payload', 'ramdisk', 'pid1', 'candidate', 'package', 'fdt',
                'layout', 'source_to_link', 'image_qualification', 'stop_protocol'}
    require(set(paths) == required, 'Image descriptor file set mismatch')
    helpers = {name: helper(main, pins, name) for name in pins['helpers']}
    memory = helpers['memory']
    def guarded_source_read(*args, **kwargs):
        stop.check()
        result = subprocess.run(*args, **kwargs)
        stop.check()
        return result
    memory.subprocess = SimpleNamespace(run=guarded_source_read)
    sources = {'commands': []}
    stop.check(); rules = memory.source_rules(main, sources)
    stop.check()
    sources['console'] = helpers['console'].preflight(main)
    facts = helpers['timer'].inspect(main, read_json(main / pins['timer_inputs']['path']), {})
    helpers['timer'].validate_launch(read_json(main / pins['timer_launch']['path']), facts)
    sources['legacy_stop'] = helpers['stop'].preflight(main, main / pins['stop_inputs']['path'])
    require(sources['legacy_stop']['outcome'] == 'pass' and
            sources['legacy_stop']['pid1_runtime_admissible'] is False, 'Legacy stop boundary changed')
    for row in pins['bindings']:
        stop.check(); binding(main, row)
    vm022 = read_json(binding(main, pins['vm022_plan']), bound=16 << 20)
    require(len(vm022['shim_source_comparison']) == 13, 'Expected thirteen matched shim source/license inputs')
    for row in vm022['shim_source_comparison']:
        stop.check()
        path = Path(row['path'])
        require(path.resolve().is_relative_to(main.resolve()) and digest(path) == row['current_sha256']
                == row['compiled_source_sha256'], 'VM022 matched shim source changed')
    lineage = read_json(paths['source_to_link'])
    require(lineage['raw_macho'] == descriptor['files']['kernel'] and
            lineage['profile'] == descriptor['profile'] and lineage['source_graph_sha256'] == pins['source_graph_sha256'],
            'Source-to-link image/profile/graph mismatch')
    require(lineage['link_command']['exit_code'] == 0 and
            isinstance(lineage['link_command']['argv'], list) and
            lineage['link_command']['argv'] and lineage['input_bindings'], 'Missing genuine link record')
    object_lineage(main, lineage, vm022['ordered_object_map'], stop)
    for row in [*lineage['input_bindings'], lineage['link_command']['stdout'], lineage['link_command']['stderr']]:
        stop.check(); binding(main, row)
    qualification = read_json(paths['image_qualification'])
    require(qualification['raw_macho'] == descriptor['files']['kernel'] and
            qualification['source_to_link'] == descriptor['files']['source_to_link'] and
            qualification['decision'] == 'admit-exact-raw-macho', 'Independent image qualification mismatch')
    candidate = read_json(paths['candidate'])
    pid_fixture = read_json(main / pins['pid1_inputs']['path'])
    helpers['pid1'].verify_inputs(main, pid_fixture)
    require(candidate in pid_fixture['qualified_candidates'] and candidate['sha256'] == descriptor['files']['pid1']['sha256'],
            'PID1 exact compiled candidate absent')
    helpers['pid1'].candidate_review(main, pid_fixture, candidate, paths['candidate'])
    package_root = paths['package'].parent
    require(paths['ramdisk'] == package_root / 'root.ramdisk' and paths['package'].name == 'package.json', 'Raw mockfs package path mismatch')
    packaged = helpers['mockfs'].verify(package_root)
    require(packaged['input_sha256'] == descriptor['files']['pid1']['sha256'], 'Raw mockfs PID1 identity mismatch')
    package = embedded_identity(memory, paths['payload'], paths['kernel'], paths['ramdisk'])
    image = memory.macho(paths['payload'], package['entries']['kernel'])
    layout = read_json(paths['layout'])
    require(layout['ram_size'] == 256 << 20 and layout['fdt_bootargs'] == APPEND, 'Exact 256MiB diagnostic layout required')
    require(layout['shim_image_size'] == sources['qualified_shim']['image_size_including_bss_stack'], 'Shim BSS/stack extent mismatch')
    memory.qemu_plan(layout, package, layout['shim_image_size'])
    checked_layout = memory.layout_check(layout, image, package, rules)
    combined = memory.command_line(package, APPEND, True, rules)
    combined_arguments(combined)
    require(checked_layout['boot_args']['commandLine'] == combined, 'Layout/final commandLine mismatch')
    protocol = read_json(paths['stop_protocol'])
    require(protocol['protocol'] == PROTOCOL and protocol['kernel'] == descriptor['files']['kernel']
            and protocol['pid1'] == descriptor['files']['pid1']
            and protocol['ramdisk'] == descriptor['files']['ramdisk']
            and protocol['combined_boot_args'] == combined
            and protocol['decision'] == 'admit-image-bound-paused-cont-stop-observations',
            'New image-bound paused/cont/PID1 stop admission required; legacy VM030 is not waived')
    props = fdt(paths['fdt'].read_bytes()) if paths['fdt'].stat().st_size <= MAX_FDT else None
    fdt_contract(props, layout, package)
    run_dir = output_dir(run_dir)
    qemu = binding(main, pins['qemu'])
    shim = binding(main, pins['shim'])
    argv = [str(qemu), '-machine', 'virt,gic-version=3', '-accel', 'tcg', '-cpu', 'cortex-a76',
            '-smp', '1', '-m', '256', '-nodefaults', '-nic', 'none', '-display', 'none',
            '-serial', 'stdio', '-monitor', 'none', '-no-reboot', '-S', '-kernel', str(shim),
            '-initrd', str(paths['payload']), '-dtb', str(paths['fdt']), '-append', APPEND,
            '-qmp', 'unix:qmp.sock,server=on,wait=off']
    return {'schema_version': 1, 'task': 'VM-040', 'owner': OWNER, 'protocol': PROTOCOL,
            'image_id': image_id, 'admission': entry, 'descriptor': descriptor,
            'collector_sha256': digest(__file__), 'fixture_sha256': digest(FIXTURE),
            'main': str(main.resolve()), 'cwd': str(run_dir), 'argv': argv, 'layout': layout,
            'package': package, 'checked_layout': checked_layout, 'combined_boot_args': combined,
            'source_preflights': sources, 'source_commands': sources['commands'],
            'deadline_seconds': DEADLINE, 'owned_rss_limit_bytes': RSS_LIMIT,
            'runtime_qualification': 'unmeasured; independent review required'}


class Stop:
    def __init__(self):
        self.reason = None

    def request(self, reason='Stop requested'):
        self.reason = reason

    def check(self):
        require(self.reason is None, self.reason or 'Stop requested')


class QMP:
    """Typed, bounded newline protocol with exact reply IDs and raw transcript."""
    def __init__(self, sock, guard, record):
        self.sock, self.guard, self.record = sock, guard, record
        self.buffer, self.sequence, self.total = b'', 0, 0
        self.sock.settimeout(.02)

    def receive(self, *, optional=False):
        while b'\n' not in self.buffer:
            self.guard()
            try:
                block = self.sock.recv(4096)
            except socket.timeout:
                if optional:
                    return None
                continue
            if not block:
                if optional and not self.buffer:
                    return None
                raise Refused('QMP closed with incomplete protocol')
            self.buffer += block; self.total += len(block)
            require(len(self.buffer) <= 65536 and self.total <= MAX_LOG, 'QMP byte budget exceeded')
        raw, self.buffer = self.buffer.split(b'\n', 1)
        message = decode_json(raw)
        require(isinstance(message, dict), 'QMP object required')
        if 'event' in message:
            require(isinstance(message['event'], str) and isinstance(message.get('data', {}), dict), 'QMP event types')
        elif 'QMP' in message:
            require(isinstance(message['QMP'], dict), 'QMP greeting types')
        else:
            require(type(message.get('id')) is int and ('return' in message) != ('error' in message), 'QMP reply types')
        require(len(self.record) < 4096, 'QMP message budget exceeded')
        self.record.append({'direction': 'received', 'at': now(), 'message': message,
                            'raw_utf8': raw.decode('utf-8')})
        return message

    def command(self, name, arguments=None):
        self.guard()
        require(name in {'qmp_capabilities', 'stop', 'query-status', 'pmemsave', 'cont'}, 'Unapproved QMP operation')
        if name == 'pmemsave':
            require(isinstance(arguments, dict) and set(arguments) == {'val', 'size', 'filename'}
                    and type(arguments['val']) is int and type(arguments['size']) is int
                    and 0x40000000 <= arguments['val'] < 0x50000000
                    and 0 < arguments['size'] <= MAX_FDT
                    and arguments['size'] <= 0x50000000 - arguments['val']
                    and arguments['filename'] in {'input-fdt-header.bin', 'input-fdt.dtb', 'apple-tree.adt'}
                    and (arguments['filename'] != 'apple-tree.adt' or arguments['size'] <= 65536), 'Typed owned QMP dump rejected')
        else:
            require(arguments is None, 'Unexpected QMP arguments')
        self.sequence += 1
        request = {'execute': name, 'id': self.sequence}
        if arguments is not None:
            request['arguments'] = arguments
        self.record.append({'direction': 'sent', 'at': now(), 'message': request})
        self.sock.sendall(json.dumps(request).encode() + b'\r\n')
        while True:
            reply = self.receive()
            if 'event' in reply:
                continue
            require(reply.get('id') == self.sequence, 'QMP unexpected reply ID')
            require('return' in reply and 'error' not in reply, 'QMP command failed')
            return reply['return']


def lease(main, lease_id, plan_path, plan, *, current=None):
    queue = main / 'artifacts/team-coordination/20261106-team/resource-queue.json'
    grant = read_json(queue)['qemu']
    require(isinstance(grant, dict), 'No root QEMU lease')
    expected = {'id': lease_id, 'owner': OWNER, 'task': 'VM-040', 'protocol': PROTOCOL,
                'plan_sha256': digest(plan_path), 'collector_sha256': digest(__file__),
                'image_descriptor_sha256': plan['admission']['descriptor']['sha256'],
                'guest_memory_mib': 256, 'owned_rss_limit_bytes': RSS_LIMIT,
                'deadline_seconds': DEADLINE, 'output': plan['cwd']}
    require(all(type(grant.get(k)) is type(v) and grant[k] == v for k, v in expected.items()), 'Exact root lease binding mismatch')
    issued = datetime.fromisoformat(grant['issued_at'])
    expiry = datetime.fromisoformat(grant['expires_at'])
    current = current or datetime.now(timezone.utc)
    require(issued.tzinfo is not None and expiry.tzinfo is not None and
            issued <= current < expiry and 0 < (expiry - issued).total_seconds() <= 600, 'Root lease stale/not active')
    return hashlib.sha256(json.dumps(grant, sort_keys=True).encode()).hexdigest()


def memory_self():
    return {line.split(':')[0]: line.split(':')[1].strip()
            for line in Path('/proc/self/status').read_text().splitlines()
            if line.startswith(('VmHWM:', 'VmRSS:'))}


def own_process(argv, cwd, supervisor, stop, *, seconds, operation=None, guard_extra=None,
                rss_limit=RSS_LIMIT, memory_floor=True):
    """Finite real process primitive; tests use only tiny owned Python children."""
    stop.check()
    require(0 < seconds <= DEADLINE, 'Finite process deadline required')
    cwd = Path(cwd)
    record = {'argv': argv, 'cwd': str(cwd), 'started_at': now(), 'samples': [],
              'qmp': [], 'host_signals': [], 'guest_started': False, 'elapsed_seconds': 0,
              'deadline_seconds': seconds, 'timed_out': False, 'stop_reason': None}
    def child_limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG, MAX_LOG))
    process = None
    start = time.monotonic()
    with (cwd / 'console.log').open('xb') as console, (cwd / 'stderr.log').open('xb') as stderr:
        try:
            stop.check()
            record['before_spawn'] = supervisor.sample()
            own_rss = int(memory_self()['VmRSS'].split()[0]) * 1024
            require(own_rss <= rss_limit, 'Controller RSS exceeds pre-spawn admission limit')
            if memory_floor:
                require(record['before_spawn']['MemAvailable_bytes'] >= 4 << 30
                        and not supervisor.pressured(record['before_spawn']),
                        'Memory availability/pressure admission revoked before spawn')
            if guard_extra:
                guard_extra()
            stop.check()
            process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=console,
                                       stderr=stderr, start_new_session=True, preexec_fn=child_limits,
                                       env={**os.environ, 'LC_ALL': 'C', 'PYTHONUTF8': '1',
                                            'PYTHONNOUSERSITE': '1', 'GIT_NO_LAZY_FETCH': '1',
                                            'GIT_OPTIONAL_LOCKS': '0'})
            record['owned_session'] = process.pid
            def guard():
                stop.check()
                elapsed = time.monotonic() - start
                if elapsed >= seconds:
                    record['timed_out'] = True
                    raise Refused('Finite owned-process deadline expired')
                snapshot = supervisor.sample(process.pid)
                record['samples'].append(snapshot)
                require(len(record['samples']) <= 8192, 'Resource sample budget exceeded')
                own_rss = int(memory_self()['VmRSS'].split()[0]) * 1024
                require(snapshot['owned_tree_rss_bytes'] + own_rss <= rss_limit, 'Owned RSS limit exceeded')
                if memory_floor:
                    require(snapshot['MemAvailable_bytes'] >= 4 << 30 and not supervisor.pressured(snapshot),
                            'Memory availability/pressure admission revoked')
                require(all((cwd / name).stat().st_size <= MAX_LOG for name in ('console.log', 'stderr.log')),
                        'Console/stderr byte bound exceeded')
                if guard_extra:
                    guard_extra()
            guard()
            if operation:
                operation(process, guard, record)
            while process.poll() is None:
                guard(); time.sleep(.02)
            process.wait(timeout=1)
        except BaseException as error:
            record['stop_reason'] = str(error)
        finally:
            if process is not None:
                before = supervisor.sample(process.pid)
                if process.poll() is None or before['owned_processes']:
                    original_signal = supervisor.group_signal
                    def traced_signal(session, sig):
                        require(session == process.pid and session > 1, 'Unowned cleanup session')
                        groups = {p['pgrp'] for p in supervisor.sample(session)['owned_processes']}
                        for group in sorted(groups):
                            attempt = {'session': session, 'pgrp': group, 'signal': signal.Signals(sig).name,
                                       'at': now(), 'result': 'pending'}
                            record['host_signals'].append(attempt)
                            try:
                                os.killpg(group, sig)
                                attempt['result'] = 'sent'
                            except ProcessLookupError:
                                attempt['result'] = 'already-absent'
                    supervisor.group_signal = traced_signal
                    try:
                        supervisor.terminate(process)
                    except BaseException as error:
                        record['cleanup_error'] = repr(error)
                    finally:
                        supervisor.group_signal = original_signal
                record['exit_code'] = process.poll()
                record['after'] = supervisor.sample(process.pid)
                record['live_owned_pids'] = [p['pid'] for p in record['after']['owned_processes']]
            else:
                record.update(exit_code=None, live_owned_pids=[])
            record['elapsed_seconds'] = time.monotonic() - start
            record['current_image_memory'] = memory_self()
    record['outputs'] = {name: {'sha256': digest(cwd / name), 'size': (cwd / name).stat().st_size}
                         for name in ('console.log', 'stderr.log')}
    return record


def protocol_operation(main, pins, plan, out):
    def operation(process, guard, record):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(.02)
        directory = os.open(out, os.O_RDONLY | os.O_DIRECTORY)
        try:
            while True:
                guard()
                endpoint = out / 'qmp.sock'
                if endpoint.exists():
                    info = endpoint.lstat()
                    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid(), 'Owned QMP socket type/owner mismatch')
                    try:
                        connection.connect('/proc/self/fd/' + str(directory) + '/qmp.sock')
                        break
                    except (FileNotFoundError, ConnectionRefusedError, socket.timeout):
                        pass
                require(process.poll() is None, 'QEMU exited before QMP greeting')
                time.sleep(.02)
            qmp = QMP(connection, guard, record['qmp'])
            require('QMP' in qmp.receive(), 'Missing QMP greeting')
            qmp.command('qmp_capabilities')
            qmp.command('stop')
            status = qmp.command('query-status')
            require(isinstance(status, dict) and status.get('running') is False
                    and status.get('status') in ('paused', 'prelaunch'), 'QMP must confirm paused input admission')
            base, capacity = plan['layout']['fdt_base'], plan['layout']['fdt_size']
            require(type(capacity) is int and 40 <= capacity <= MAX_FDT, 'Declared FDT capture capacity')
            require(not (out / 'input-fdt-header.bin').exists() and
                    not (out / 'input-fdt-header.bin').is_symlink(), 'FDT header output must be new')
            qmp.command('pmemsave', {'val': base, 'size': 40, 'filename': 'input-fdt-header.bin'})
            header = inside(out, 'input-fdt-header.bin')
            require(header.stat().st_size == 40, 'Input FDT header capture size')
            magic, length = struct.unpack('>II', header.read_bytes()[:8])
            require(magic == 0xd00dfeed and 40 <= length <= capacity, 'Runtime Linux FDT length/magic')
            require(not (out / 'input-fdt.dtb').exists() and
                    not (out / 'input-fdt.dtb').is_symlink(), 'FDT output must be new')
            qmp.command('pmemsave', {'val': base, 'size': length, 'filename': 'input-fdt.dtb'})
            capture = inside(out, 'input-fdt.dtb')
            require(capture.stat().st_size == length, 'Input FDT exact capture length')
            parsed = fdt(capture.read_bytes())
            record['input_fdt'] = {**fdt_contract(parsed, plan['layout'], plan['package']),
                                   'address': base, 'size': length, 'sha256': digest(capture),
                                   'before_cont': True, 'Apple_serialized_tree': False}
            guard(); qmp.command('cont')
            record['cont_acknowledged_at'] = now()
            record['apple_tree'] = {'outcome': 'unmeasured', 'reason': 'No post-shim checkpoint captured before guest stop'}
            while process.poll() is None:
                guard(); qmp.receive(optional=True)
                if record['apple_tree']['outcome'] == 'unmeasured':
                    console = (out / 'console.log').read_bytes()
                    extents = re.findall(rb'avfboot: device tree (0x[0-9a-f]+)\+(0x[0-9a-f]+) boot_args (0x[0-9a-f]+)', console)
                    require(len(extents) <= 1, 'Repeated shim Apple-tree checkpoint')
                    if extents and process.poll() is None:
                        address, length, boot = (int(v, 16) for v in extents[0])
                        low, high = plan['checked_layout']['apple_device_tree_capacity']
                        require(address == low and 0 < length <= min(65536, high - low)
                                and boot == plan['checked_layout']['boot_args_page'][0], 'Post-shim Apple-tree extent mismatch')
                        require(not (out / 'apple-tree.adt').exists() and
                                not (out / 'apple-tree.adt').is_symlink(), 'Apple tree output must be new')
                        qmp.command('stop')
                        status = qmp.command('query-status')
                        require(status.get('running') is False and status.get('status') == 'paused', 'Post-shim capture must be paused')
                        qmp.command('pmemsave', {'val': address, 'size': length, 'filename': 'apple-tree.adt'})
                        path = inside(out, 'apple-tree.adt')
                        require(path.stat().st_size == length, 'Apple tree exact capture length')
                        tree = helper(main, pins, 'tree')
                        _data, nodes = tree.read_tree(path)
                        record['apple_tree'] = {'outcome': 'captured-parser-pass', 'source_checkpoint': extents[0][0].decode(),
                                                'address': address, 'size': length, 'sha256': digest(path),
                                                'preflight': tree.preflight(nodes, require_ramdisk=True),
                                                'genuine_kernel_evidence': False}
                        qmp.command('cont')
            # Drain buffered shutdown events before closing the socket.
            while qmp.receive(optional=True) is not None:
                pass
        finally:
            connection.close(); os.close(directory)
    return operation


def collect(plan_path, lease_id, stop):
    stop.check()
    plan = read_json(plan_path, bound=16 << 20)
    main = Path(plan['main'])
    require(Path(plan_path).absolute() == Path(plan_path).resolve() and
            Path(plan_path).resolve().is_relative_to((ROOT / 'artifacts/avf-kernel-boot').resolve()),
            'Plan must be canonical inside collector artifacts')
    fresh = prepare(main, plan['image_id'], Path(plan['cwd']), stop)
    # Source command timings vary; every operative vector and digest must match.
    for key in ('admission', 'descriptor', 'collector_sha256', 'fixture_sha256', 'argv',
                'cwd', 'layout', 'package', 'checked_layout', 'combined_boot_args'):
        require(fresh[key] == plan[key], 'Plan changed before launch: ' + key)
    initial_lease = lease(main, lease_id, plan_path, plan)
    pins = read_json(FIXTURE)
    supervisor = helper(main, pins, 'process')
    for sample_index in range(3):
        stop.check()
        require(lease(main, lease_id, plan_path, plan) == initial_lease, 'Root lease changed')
        sample = supervisor.sample()
        require(sample['MemAvailable_bytes'] >= 4 << 30 and not supervisor.pressured(sample), 'Stable memory admission failed')
        if sample_index < 2:
            time.sleep(1)
    out = output_dir(plan['cwd']); out.mkdir(parents=True, exist_ok=False)
    def running_lease():
        require(lease(main, lease_id, plan_path, plan) == initial_lease, 'Root lease changed/revoked')
    operation = protocol_operation(main, pins, plan, out)
    record = own_process(plan['argv'], out, supervisor, stop, seconds=DEADLINE,
                         operation=operation, guard_extra=running_lease)
    record['guest_started'] = bool(record.get('cont_acknowledged_at'))
    record.update(protocol=PROTOCOL, plan_sha256=digest(plan_path), lease_id=lease_id,
                  lease_entry_sha256=initial_lease, image_descriptor_sha256=plan['admission']['descriptor']['sha256'],
                  combined_boot_args=plan['combined_boot_args'], source_to_link=plan['descriptor']['files']['source_to_link'])
    events = [item['message'] for item in record['qmp'] if item['direction'] == 'received' and 'event' in item['message']]
    received = [item['message'].get('event') for item in record['qmp'] if item['direction'] == 'received']
    record['qmp_events'] = events
    record['resume_observed'] = 'RESUME' in received
    try:
        record['console_diagnostic'] = helper(main, pins, 'console').diagnose(out / 'console.log')
        frozen = helper(main, pins, 'stop')
        record['legacy_VM030_baseline'] = frozen.classify((out / 'console.log').read_bytes(), events,
            {'guest_started': record['guest_started'], 'argv': record['argv'], 'boot_args': plan['combined_boot_args'],
             'termination': {key: record[key] for key in ('timed_out', 'host_signals', 'live_owned_pids',
                                                         'exit_code', 'elapsed_seconds', 'deadline_seconds')}}, 'pid1-panic')
        record['observation_assessment'] = assess_observations((out / 'console.log').read_bytes(), events, record)
    except (ValueError, KeyError, TypeError, OSError) as error:
        record['observation_assessment'] = {'classification': 'inconclusive', 'error': str(error)}
    write_json(out / 'qmp-events.json', events)
    write_json(out / 'qmp-transcript.json', record['qmp'])
    for name in ('input-fdt-header.bin', 'input-fdt.dtb', 'apple-tree.adt', 'qmp-events.json', 'qmp-transcript.json'):
        if (out / name).is_file() and not (out / name).is_symlink():
            record['outputs'][name] = {'sha256': digest(out / name), 'size': (out / name).stat().st_size}
    write_json(out / 'supervisor.json', record)
    return record


def assess_observations(console, events, record):
    """New protocol observations; frozen VM030 admission is never overridden."""
    require(isinstance(console, bytes) and len(console) <= MAX_LOG, 'Bounded raw console required')
    reasons = []
    require(isinstance(events, list) and all(isinstance(e, dict) and isinstance(e.get('data', {}), dict)
                                           for e in events), 'Typed QMP events required')
    for token in (b'Darwin Kernel Version', b'VM002: pid=1 ostype=Darwin owned-entry=v1',
                  b'avf: powering off (PSCI SYSTEM_OFF)', b'avfboot: jumping to XNU at',
                  b'avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt'):
        if console.count(token) != 1:
            reasons.append('Expected exactly one marker: ' + token.decode())
    tokens = [b'Darwin Kernel Version', b'VM002: pid=1 ostype=Darwin owned-entry=v1',
              b'avf: kernel panic: panic(', b'avf: powering off (PSCI SYSTEM_OFF)']
    positions = [console.find(token) for token in tokens]
    if any(pos < 0 for pos in positions) or positions != sorted(positions):
        reasons.append('Single-boot identity/critical-initproc panic/PSCI sequence absent')
    if not any(token in console for token in (b'initproc failed to start', b'initproc exited')):
        reasons.append('Expected critical initproc panic absent')
    critical = [console.find(token) for token in (b'initproc failed to start', b'initproc exited') if token in console]
    if (len(critical) != 1 or sum(console.count(token) for token in
            (b'initproc failed to start', b'initproc exited')) != 1
            or not positions[2] <= critical[0] < positions[3]):
        reasons.append('Critical initproc panic ordering is not established')
    if console.count(b'avf: kernel panic: panic(') != 1:
        reasons.append('Repeated or missing kernel panic')
    bootlines = re.findall(rb'^avfboot: boot-args: (.*)\r?$', console, re.M)
    if len(bootlines) != 1 or bootlines[0].rstrip(b'\r') != record.get('combined_boot_args', '').encode():
        reasons.append('Actual final shim boot args do not bind the complete vector')
    shim_positions = [console.find(token) for token in
        (b'avfboot: HakiOS XNU boot for crosvm/AVF and QEMU virt', b'avfboot: boot-args:',
         b'avfboot: jumping to XNU at', b'Darwin Kernel Version')]
    if any(pos < 0 for pos in shim_positions) or shim_positions != sorted(shim_positions):
        reasons.append('Shim/argument/jump/kernel ordering is not established')
    if any(token in console.lower() for token in (b'synthetic', b'avfboot: fatal:', b'firmware refused')):
        reasons.append('Synthetic/shim failure/firmware refusal recorded')
    shutdowns = [event for event in events if event.get('event') == 'SHUTDOWN']
    if len(shutdowns) != 1 or shutdowns[0].get('data', {}).get('guest') is not True or shutdowns[0].get('data', {}).get('reason') != 'guest-shutdown':
        reasons.append('Exactly one guest-origin QMP shutdown required')
    if any(event.get('event') in {'RESET', 'GUEST_PANICKED'} for event in events):
        reasons.append('Unexpected reset/paravirtual panic event')
    if any(token in console for token in (b'avf: halt (PSCI SYSTEM_OFF)', b'avf: reboot (PSCI SYSTEM_RESET)')):
        reasons.append('Unexpected additional kernel PSCI intent')
    if record.get('resume_observed') is not True or not record.get('cont_acknowledged_at') or not record.get('input_fdt'):
        reasons.append('Paused Linux FDT admission and explicit cont/RESUME not established')
    if (type(record.get('exit_code')) is not int or record['exit_code'] != 0
            or record.get('live_owned_pids') != [] or record.get('stop_reason')
            or record.get('guest_started') is not True):
        reasons.append('Clean in-deadline owned process exit not established')
    elapsed, deadline = record.get('elapsed_seconds'), record.get('deadline_seconds')
    if type(elapsed) not in (int, float) or type(deadline) not in (int, float) or not 0 <= elapsed < deadline <= DEADLINE:
        reasons.append('Finite actual termination interval not established')
    if record.get('host_signals') != [] or record.get('timed_out') is not False:
        reasons.append('Host cleanup cannot establish guest shutdown')
    return {'classification': 'consistent-observations-awaiting-review' if not reasons else 'inconclusive',
            'reasons': reasons, 'genuine_kernel_qualified': False, 'pid1_runtime_qualified': False,
            'PSCI_instruction_traced': False, 'legacy_VM030_admission': 'unchanged; -S/PID1 remains rejected',
            'repeated_boot_protocol': 'unsupported; repeated markers reject'}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, indent=2, allow_nan=False); stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--main', type=Path, required=True)
    plan.add_argument('--image', default='current')
    plan.add_argument('--run-dir', type=Path, required=True)
    plan.add_argument('--out', type=Path, required=True)
    run = commands.add_parser('run')
    run.add_argument('--plan', type=Path, required=True)
    run.add_argument('--lease-id', required=True)
    args = parser.parse_args()
    stop = Stop()
    previous = {sig: signal.signal(sig, lambda signum, frame: stop.request('Host Stop signal ' + str(signum)))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        stop.check()
        if args.action == 'plan':
            require(args.out.absolute() == args.out.resolve() and not args.out.exists()
                    and args.out.resolve().is_relative_to((ROOT / 'artifacts/avf-kernel-boot').resolve()),
                    'Plan output must be new/canonical inside collector artifacts')
            result = prepare(args.main.resolve(), args.image, args.run_dir, stop)
            stop.check(); write_json(args.out, result)
            print('Prepared exact image-bound collector plan; no guest started')
            return 0
        result = collect(args.plan.resolve(), args.lease_id, stop)
        print('Collected observations; independent genuine-kernel/runtime review required')
        return 0 if result['observation_assessment']['classification'] == 'consistent-observations-awaiting-review' else 2
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        print('Collector refused or stopped: ' + str(error), file=sys.stderr)
        return 2
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == '__main__':
    sys.exit(main())
