#!/usr/bin/env python3
"""Independent bounded review of frozen VM008 bytes; executes no build tools."""
import collections
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import struct
import sys
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
SOURCE = MAIN / 'worktrees/vm-008-20261105'
H = SOURCE / 'artifacts/avf-kernel-headers'
OUT = Path(__file__).resolve().parent / 'verification.json'
started = time.monotonic()
checks = 0
bindings = {}
result = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
          'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'argv': [sys.executable, *sys.argv], 'checks': 0, 'compiler_generator_guest_started': False}


def expect(condition, label):
    global checks
    checks += 1
    if not condition:
        raise ValueError(label)
    if time.monotonic() - started > 180:
        raise TimeoutError('180s review deadline')
    usage = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:', 'VmRSS:')))
    if int(usage['VmHWM'].split()[0]) * 1024 > 256 * 1024**2:
        raise MemoryError('Current image VmHWM exceeds 256MiB')


def digest(path):
    path = Path(path)
    if str(path) not in bindings:
        with path.open('rb') as stream:
            bindings[str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return bindings[str(path)]


def bound(path, wanted):
    expect(digest(path) == wanted, 'SHA256 binding: ' + str(path))


def read(path):
    return json.loads(Path(path).read_text())


def macho(path):
    sections = []
    with Path(path).open('rb') as stream:
        header = stream.read(32)
        expect(len(header) == 32, 'Mach-O header size')
        magic, cpu, subtype, kind, count, extent, flags, reserved = struct.unpack('<8I', header)
        expect((magic, cpu, kind) == (0xfeedfacf, 0x100000c, 1), 'ARM64 Mach-O relocatable identity')
        length = Path(path).stat().st_size
        end = 32 + extent
        expect(end <= length, 'Mach-O command extent')
        for unused in range(count):
            at = stream.tell()
            command, size = struct.unpack('<II', stream.read(8))
            expect(size >= 8 and at + size <= end, 'Mach-O command bounds')
            data = stream.read(size - 8)
            if command == 0x19:
                nsects = struct.unpack_from('<I', data, 56)[0]
                expect(size >= 72 + 80 * nsects, 'Mach-O segment section table')
                for index in range(nsects):
                    name, segment, address, section_size, offset = struct.unpack_from('<16s16sQQI', data, 64 + 80 * index)
                    name, segment = name.split(b'\0')[0].decode(), segment.split(b'\0')[0].decode()
                    if 'kalloc' in name:
                        expect(section_size > 0 and offset + section_size <= length, 'Allocator section bytes present')
                        position = stream.tell()
                        stream.seek(offset)
                        content = stream.read(section_size)
                        stream.seek(position)
                        sections.append({'section': name, 'segment': segment, 'size': section_size, 'sha256': hashlib.sha256(content).hexdigest()})
        expect(stream.tell() == end, 'Mach-O exact load commands')
    return sections


try:
    ledger = read(MAIN / 'state/lab.json')
    plan = next(e for e in ledger['experiments'] if e['id'] == 'REVHEAD-001')
    expect(plan['task'] == 'REV-023' and plan['owner'] == 'codex-review-integration-20261106-ct', 'Real pre-registered review plan')
    del ledger
    descriptor_path = SOURCE / 'fixtures/public/avf-kernel-headers/qualified-component.json'
    evidence_path = SOURCE / 'docs/procedures/avf-kernel-headers/evidence.json'
    bound(descriptor_path, '058451939894bd48ccc2ad1fe8b8d85c515f2176d21c8025daa034be8e98abe7')
    bound(evidence_path, '6209dde21ba80535e3cc15139dc6165b5e120674920b9382257dddab3fa9fbf1')
    d, evidence = read(descriptor_path), read(evidence_path)
    bound(SOURCE / d['implementation']['path'], d['implementation']['sha256'])
    for path, wanted in evidence['sha256'].items():
        bound(MAIN / path, wanted)
    index = read(MAIN / d['artifact_index'])['files']
    expect(len(index) == 53976, 'Frozen complete-index cardinality; no broad rehash')
    phases = {name: read(MAIN / path) for name, path in d['accepted_phase_reports'].items()}
    for name, report in phases.items():
        expect(report['outcome'] == 'pass', 'Accepted phase outcome: ' + name)
        for command in report['commands']:
            expect(command['exit_code'] in (0, 1, 2), 'Finite recorded command exit')
            expect(not any(p['state'] != 'Z' for p in command.get('after', {}).get('owned_processes', [])), 'No recorded surviving child')
        if 'prepared_parent' in report:
            parent = report['prepared_parent']
            bound(parent['path'], parent['sha256'])
    prepared = read(MAIN / d['prepared_component'])
    composition = read(prepared['parent_source']['composition_manifest'])['profiles']['qemu']
    bound(prepared['parent_source']['composition_manifest'], prepared['parent_source']['composition_manifest_sha256'])
    expect(composition['canonical_output_tree'] == '6a955269a8f4e17d21239f75cef9fbe66cffc56c', 'Accepted QEMU source tree')
    expect(composition['source_config_sha256'] == '1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394', 'Accepted guest config')
    bound(Path(prepared['donor_root']) / '.config', composition['source_config_sha256'])
    original_source = {r['path']: r['sha256'] for r in composition['files']}
    kernel = Path(prepared['kernel_root'])
    for name, tool in prepared['public_host_tools'].items():
        bound(tool.get('path', tool.get('source')), tool['sha256'])
    bound(prepared['compiler']['path'], prepared['compiler']['sha256'])
    headers = read(H / 'headers-final-1/installed-header-manifest.json')
    expect(len(headers) == 1905, 'Complete selected header entries')
    counts = collections.Counter(row['status'] for row in headers)
    expect(counts == {'installed': 1869, 'genuine_filter_removed_empty_body': 36}, 'Materialized/filtered counts')
    expect(len({r['output'] for r in headers}) == len(headers), 'Unique header destinations')
    queries = phases['initial-headers']['header_queries']
    initial = read(H / 'headers-2/header-inventory.json')
    covered = []
    for query in queries:
        for row_index in query['rows']:
            row = initial[row_index]
            expect(row['name'] in query['values'][row['kind']].split(), 'Header selected by genuine queried list')
            covered.append(row_index)
    expect(sorted(covered) == list(range(1905)), 'All namespace rows covered once by selection queries')
    for position, row in enumerate(headers):
        old = initial[position]
        expect(all(row[key] == old[key] for key in ('declaration', 'kind', 'name', 'private', 'generated_input', 'unifdef_flags')), 'Final namespace keeps exact queried selection')
        expect(Path(row['output']).relative_to(H/'headers-final-1/installtree') == Path(old['output']).relative_to(H/'headers-2/installtree'), 'Final namespace keeps exact selected destinations')
        bound(row['declaration'], row['declaration_sha256'])
        bound(row['source'], row['source_sha256'])
        expect(all(flag in row['unifdef_flags'] for flag in ('-UXNU_KERNEL_PRIVATE', '-UMACH_KERNEL_PRIVATE', '-UBSD_KERNEL_PRIVATE')), 'Installed private implementation filtering')
        source = Path(row['source'])
        if source.is_relative_to(kernel):
            bound(source, original_source[str(source.relative_to(kernel))])
        if row.get('generated_origin'):
            bound(row['generated_origin'], row['source_sha256'])
        output = Path(row['output'])
        if row['status'] == 'installed':
            bound(output, row['output_sha256'])
            expect(output.stat().st_mode & 0o777 == 0o444, 'Read-only installed mode')
        else:
            expect(not output.exists(), 'Filtered-empty destination absent')
    thread = next(Path(r['output']) for r in headers if r['private'] and r['output'].endswith('/kern/thread.h'))
    expect(not re.search(r'\bstruct\s+thread\s*\{', thread.read_text()), 'Installed thread implementation body removed')
    rows = read(MAIN / d['next_object_manifest'])
    expect(len(rows) == 1080 and len({r['id'] for r in rows}) == 1080, 'Unique next component slots')
    expect(sum(r['generated_input'] for r in rows) == 55, '55 actual generated sources')
    for component, config in prepared['configurations'].items():
        path = Path(config['root']) / 'Makefile'
        bound(path, config['makefile_sha256'])
        text = path.read_text().replace('\\\n', ' ')
        selected = re.findall(r'^OBJS\s*=(.*)$', text, re.M)
        expect(len(selected) == 1 and set(selected[0].split()) == {r['target'] for r in rows if r['component'] == component}, 'Exact real component OBJS selection: ' + component)
    generated_candidates = {str(H / 'mig-1' / name) for name in read(H / 'mig-1/mig-component.json')['outputs']}
    generated_candidates |= {name for pair in read(H / 'iig-1/iig-component.json')['pairs'].values() for name in pair['outputs']}
    generated_candidates |= {str(H / 'syscalls-2/build/bsd' / name) for name in ('init_sysent.c', 'syscalls.c', 'systrace_args.c')}
    generated_candidates.add(str(Path(prepared['configurations']['bsd']['root']) / 'ioconf.c'))
    for row in rows:
        bound(row['bound_source'], row['bound_source_sha256'])
        bound(row['configuration'], row['configuration_sha256'])
        if not row['generated_input']:
            bound(row['bound_source'], original_source[str(Path(row['bound_source']).relative_to(kernel))])
        else:
            expect(row['bound_source'] in generated_candidates, 'Generated source bound to genuine producer output')
        command = row['next_owned_compile_argv_template']
        recipe = shlex.split(row['genuine_expanded_recipe'])
        expect(command[0] == prepared['compiler']['path'] and '-c' in command, 'Actual compiler retained')
        expect('-DXNU_NO_TYPE_BUILTINS=0' in command and '-target' in command and command[command.index('-target')+1] == 'arm64-apple-ios16.5', 'Real allocator/guest target flags')
        expect(command[command.index('-o')+1] == '@NEXT_OBJECT_DIR@/' + row['id'], 'New output placeholder')
        expect(command[command.index('-MF')+1] == '@NEXT_DEPENDENCY_DIR@/' + row['id'] + '.d', 'New dependency placeholder')
        expect(row['bound_source'] in command and row['execution_requires_new_plan_and_resource_lease'] is True, 'Exact source and execution boundary')
        expect((Path(row['cwd']) / recipe[-1]).resolve() == Path(row['source']).resolve(), 'Expanded genuine recipe primary source')
    generated = read(H / 'handoff-1/generated-export-manifest.json')
    expect(len(generated) == 75, '75 genuine generated raw exports')
    for row in generated:
        bound(row['source'], row['sha256']); bound(row['output'], row['sha256'])
    mig = read(H / 'mig-1/mig-component.json')
    expect(len(mig['outputs']) == 127 and phases['mig']['unique_mig_commands'] == 80, '80 MIG invocations and127 products')
    for name, wanted in mig['outputs'].items():
        bound(H / 'mig-1' / name, wanted)
    for name, wanted in mig['dependencies'].items():
        bound(name, wanted)
    for trace in sorted((H / 'mig-1/preprocessing').iterdir()):
        provenance = read(trace / 'provenance.json')
        expect(provenance['exit_code'] == 0, 'Actual MIG preprocessing successful')
        bound(trace / 'input.c', provenance['temporary_sha256'])
        bound(trace / 'output.i', provenance['preprocessed_sha256'])
        for name, wanted in provenance['inputs'].items():
            bound(name, wanted)
        body = (trace / 'input.c').read_bytes()
        match = re.match(rb'#line 1 "([^"\n]+)"\n', body)
        expect(match is not None, 'MIG temporary source line identity')
        source = Path(os.fsdecode(match[1]))
        expect(source.is_relative_to(kernel) and body[match.end():] == source.read_bytes(), 'Temporary MIG bytes equal exact selected .defs')
    iig = phases['public-iig']
    expect(len(iig['iig_generation']) == 17, '17 public IIG IDLs')
    for row in iig['iig_generation'].values():
        bound(row['source'], row['source_sha256'])
        for name, wanted in row['outputs'].items():
            bound(name, wanted)
    identity = read(H / 'qualified-1d8ebf6/iig-byte-identity.json')
    expect(identity['all_byte_identical'] is True and identity['outputs'] == 34, '34 corrected-controller IIG products byte-identical')
    expect(0 < iig['host_controller_peak_rss_bytes'] <= 256 * 1024**2, 'Corrected current-image controller budget')
    objects = {}
    independently_parsed_sections = {}
    for path in d['accepted_object_records']:
        report = read(MAIN / path)
        records = report['representative_compiles'] if isinstance(report, dict) else report
        for row in records:
            expect(row['actual_arm64_object'] and row['exit_code'] == 0, 'Successful real representative')
            bound(row['source'], row['source_sha256']); bound(row['object'], row['object_sha256'])
            sections = macho(row['object'])
            independently_parsed_sections[row['id']] = sections
            if 'allocator_metadata_sections' in row:
                expect(sections == row['allocator_metadata_sections'], 'Independent allocator section parse equals recorded metadata')
            for name, wanted in row['dependencies'].items():
                bound(name, wanted)
            if isinstance(report, dict):
                commands = [c for c in report['commands'] if row['source'] in c['argv'] and c['argv'][0] == prepared['compiler']['path']]
                expect(len(commands) == 1, 'One real source compile command for representative')
                command = commands[0]
                expect(command['exit_code'] == 0 and command['argv'][command['argv'].index('-o')+1] == row['object'], 'Actual source compile emits witnessed object')
                expect('-DXNU_NO_TYPE_BUILTINS=0' in command['argv'], 'Real metadata builtins enabled in representative compile')
            objects[row['id']] = row
    expect(len(objects) == 10, '10 distinct actual guest object identities')
    metadata = objects['libkern/OSData.cpo']['allocator_metadata_sections']
    expect(sum(s['size'] for s in metadata) == 192 and any(s['section'] == '__kalloc_type' and s['segment'] == '__DATA_CONST' for s in metadata), 'Actual192-byte allocator type section')
    controls = phases['controls']['negative_controls']
    expect(len(controls) == 4 and all(r['pass'] for r in controls), 'Four preserved negatives')
    for name in ('wrong-profile', 'wrong-config'):
        report = read(H / 'controls-5' / name / 'result/report.json')
        expect(report['outcome'] == 'fail' and not report['commands'], 'Wrong input rejected before commands: ' + name)
    negative = next(r for r in controls if r['name'] == 'actual-mig-preprocessor-error')
    for path, wanted in negative['quarantined_partial_outputs'].items():
        bound(path, wanted)
    expect(negative['actual_exit_code'] == negative['preprocessor_exit_code'] == 1 and negative['no_positive_component_published'] and not (H/'controls-5/mig-component.json').exists(), 'Partial MIG outputs quarantined')
    diagnostics = (H/'controls-5/control-stock-compiler-metadata.stderr.txt').read_text()
    diagnostic_path = H/'controls-5/control-stock-compiler-metadata.stderr.txt'
    bound(diagnostic_path, index[str(diagnostic_path.relative_to(MAIN))])
    expect('__builtin_xnu_type' in diagnostics and 'error:' in diagnostics and not (H/'controls-5/stock-compiler-negative.o').exists(), 'Stock compiler fails at real XNU metadata')
    detected = False
    try:
        bound(descriptor_path, '0' * 64)
    except ValueError:
        detected = True
    expect(detected, 'Changed expected hash is rejected')
    invalid = Path(__file__).resolve().parent / 'invalid-object-control.bin'
    invalid.write_bytes(b'\0' * 32)
    detected = False
    try:
        macho(invalid)
    except ValueError:
        detected = True
    expect(detected, 'Invalid Mach-O identity is rejected')
    result['detector_controls'] = {'wrong_expected_hash_rejected': True, 'invalid_macho_rejected': True}
    for path, wanted in list(bindings.items()):
        key = str(Path(path).relative_to(MAIN))
        if key in index:
            expect(wanted == index[key], 'Independent binding agrees with frozen full index')
    expect(all(d[key] is False for key in ('sdk_qualified', 'private_apple_abi_qualified', 'full_kernel_build_or_link', 'guest_executed', 'device_executed', 'native_device_qualified')), 'Bounded qualification claims preserved')
    result.update(outcome='pass', header_counts=dict(counts), selected_next_objects=len(rows), generated_sources=55,
                  actual_distinct_objects=len(objects), metadata=metadata, independently_parsed_sections=independently_parsed_sections, negative_controls=4, objects=sorted(objects),
                  full_index_rehashed=False, source_descriptor_sha256=digest(descriptor_path))
except Exception as error:
    result['error'] = repr(error)
finally:
    usage = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:', 'VmRSS:')))
    result.update(checks=checks, elapsed_seconds=round(time.monotonic()-started,3), bindings=bindings,
                  current_image_peak_rss_bytes=int(usage['VmHWM'].split()[0])*1024,
                  current_rss_bytes=int(usage['VmRSS'].split()[0])*1024,
                  raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)
    OUT.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('bindings','objects')}))
sys.exit(0 if result['outcome'] == 'pass' else 1)
