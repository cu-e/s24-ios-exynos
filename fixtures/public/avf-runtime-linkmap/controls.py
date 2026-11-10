#!/usr/bin/env python3
"""Registered VM047 host controls; synthetic maps never count as real linking."""
import argparse
from contextlib import ExitStack
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
import traceback


CORE_SHA = '0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464'
BASE = 0xfffffff007004000
PC = BASE + 496


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            result.update(block)
    return result.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def image_bytes():
    strings = b'\0__start\0___divtc3\0'
    size = 544 + len(strings)
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 3, 464, 0, 0)
    segment = struct.pack('<II16s4Q4I', 25, 152, b'__TEXT', BASE, size, 0, size, 5, 5, 1, 0)
    section = struct.pack('<16s16sQQ8I', b'__text', b'__TEXT', PC, 16, 496, 2, 0, 0, 0, 0, 0, 0)
    symtab = struct.pack('<6I', 2, 24, 512, 2, 544, len(strings))
    state = [0] * 34
    state[32] = PC
    thread = struct.pack('<4I34Q', 5, 288, 6, 68, *state)
    symbols = struct.pack('<IBBHQ', 1, 0x0f, 1, 0, PC)
    symbols += struct.pack('<IBBHQ', 9, 0x0f, 1, 0, PC + 4)
    return header + segment + section + symtab + thread + b'\0' * 16 + symbols + strings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--main', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    observations, samples = [], []
    evidence = {'kind': 'host-test', 'origin': 'local-host', 'task': 'VM-047',
                'owner': 'codex-guest-linkmap-witness-20261106-fb',
                'recorded_at': datetime.now(timezone.utc).isoformat(),
                'outcome': 'fail', 'summary': 'VM047 controls did not complete',
                'synthetic_map_and_image': True, 'actual_link_started': False,
                'compiler_started': False, 'archive_command_started': False,
                'actual_selected_runtime_success_measured': False,
                'commands': [{'argv': sys.argv, 'exit_code': None}],
                'artifacts': [], 'controls': observations}
    exit_code = 1
    try:
        for number in range(3):
            available = next(int(line.split()[1]) * 1024 for line in
                             Path('/proc/meminfo').read_text().splitlines()
                             if line.startswith('MemAvailable:'))
            samples.append(available)
            if available < 4 * 1024**3:
                raise RuntimeError('Stable4GiB floor not available; no controls started')
            if number < 2:
                time.sleep(1)
        wt = Path(__file__).resolve().parents[3]
        source = wt / 'tools/build/avf_guest_runtime_linkmap.py'
        core_path = args.main / 'worktrees/vm-022-link-correction-20261106/tools/build/avf_guest_link_inputs.py'
        if digest(core_path) != CORE_SHA:
            raise RuntimeError('Borrowed core source differs from frozen API')
        sys.path.insert(0, str(core_path.parent))
        core = load_module('vm047_borrowed_cu_core', core_path)
        mod = load_module('vm047_runtime_map', source)
        archive = args.main / 'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive/lib/darwin/libclang_rt.cc_kext_ios.a'
        catalog_path = args.main / 'worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/archive-members.json'
        catalog = json.loads(catalog_path.read_text())
        descriptor_path = Path(__file__).with_name('source-contract.json').resolve()
        descriptor = json.loads(descriptor_path.read_text())
        with ExitStack() as stack:
            descriptor_snapshot = stack.enter_context(core.CoherentFile(descriptor_path))
            sources = {row[key]: stack.enter_context(core.CoherentFile(args.main / row[key]))
                       for row in descriptor['files'] for key in ('path', 'reference_path')}
            linker_snapshot = stack.enter_context(core.CoherentFile(args.main /
                'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'))
            source_witness = mod.qualify_sources(descriptor_snapshot, sources, linker_snapshot)
            save(args.out / 'source-witness.json', source_witness)
            observations.append({'name': 'actual-reference-linker-source-pins', 'outcome': 'pass'})
        def case(name, mutation=None, rejected=False):
            directory = args.out / name
            directory.mkdir()
            image = directory / 'synthetic-image.macho'
            map_path = directory / 'synthetic-map.txt'
            object_list = directory / 'synthetic-object-list.json'
            image.write_bytes(image_bytes())
            member = lambda n: str(archive) + '(' + catalog[n]['name'] + ')'
            rows = [f'# Path: {image}', '# Arch: arm64', '# Object files:',
                    '[  0] linker synthesized', '[  1] ' + member(0), '[  2] ' + member(2),
                    '# Sections:', '# Address\tSize    \tSegment\tSection',
                    f'0x{PC:08X}\t0x00000010\t__TEXT\t__text', '# Symbols:',
                    '# Address\tSize    \tFile  Name',
                    f'0x{PC:08X}\t0x00000004\t[  0] __start',
                    f'0x{PC+4:08X}\t0x00000004\t[  2] ___divtc3', '',
                    '# Dead Stripped Symbols:', '#        \tSize    \tFile  Name',
                    '<<dead>> \t0x00000004\t[  1] dead control atom']
            document = {'schema': 'avf-guest-link-object-list-v1', 'source_only': False,
                        'objects': [], 'archives': [{'role': 'runtime', 'path': str(archive),
                            'sha256': mod.LINEAGE['runtime_archive_sha256'],
                            'members': [dict(ordinal=i, name=r['name'], sha256=r['sha256'])
                                        for i, r in enumerate(catalog)]}],
                        'actual_link_argv': ['qualified-ld64', '-o', str(image), str(archive),
                                             '-map', str(map_path), '-why_load']}
            contract = {'schema': 'avf-runtime-linkmap-contract-v1',
                        'measurement_origin': 'synthetic-control', 'source_only': False,
                        'lineage': dict(mod.LINEAGE),
                        'source_descriptor_sha256': mod.SOURCE_DESCRIPTOR_SHA256,
                        'architecture': 'arm64', 'output_path': str(image),
                        'required_members': [2], 'diagnostic_argv': mod.diagnostic_options(str(map_path))}
            state = {'rows': rows, 'document': document, 'contract': contract,
                     'archive': archive, 'catalog': catalog_path, 'image': image}
            if mutation:
                mutation(state)
            map_path.write_text('\n'.join(state['rows']) + '\n')
            save(object_list, state['document'])
            paths = dict(image=image, map=map_path, archive=state['archive'],
                         catalog=state['catalog'], object_list=object_list)
            contract['bindings'] = {key: {'path': str(path), 'sha256': digest(path)}
                                    for key, path in paths.items()}
            if 'after_bind' in state:
                state['after_bind'](contract)
            save(directory / 'contract.json', contract)
            try:
                with ExitStack() as stack:
                    image_snapshot, view = stack.enter_context(core.macho_snapshot(image, image=True))
                    snapshots = {key: stack.enter_context(core.CoherentFile(path))
                                 for key, path in paths.items() if key != 'image'}
                    if 'view' in state:
                        state['view'](view)
                    result = mod.validate(image_snapshot, view, contract,
                        map_snapshot=snapshots['map'], archive_snapshot=snapshots['archive'],
                        object_list_snapshot=snapshots['object_list'], catalog_snapshot=snapshots['catalog'])
                if rejected:
                    raise AssertionError('Expected rejection: ' + name)
                assert result['product_authority'] is False
                assert result['qualified_for_actual_selection'] is False
                assert result['actual_execution_authenticated'] is False
                assert result['members'][0]['live_atom_count'] == 0
                assert result['members'][1]['ordinal'] == 2
                assert result['selected_symbols'][0]['name'] == '___divtc3'
                assert [r['name'] for r in result['selected_member_import_candidates']] == ['_logbl', '_scalbnl']
                save(directory / 'witness.json', result)
                observations.append({'name': name, 'outcome': 'pass', 'expected': 'byte-facts-only'})
            except ValueError as exc:
                if not rejected:
                    raise
                observations.append({'name': name, 'outcome': 'pass', 'expected': 'reject', 'reason': str(exc)})
        case('synthetic-positive-real287-archive')
        case('caller-actual-label-never-authenticates', lambda s:
             s['contract'].update(measurement_origin='actual-link'))
        for field in mod.LINEAGE:
            case('wrong-lineage-' + field, lambda s, f=field:
                 s['contract']['lineage'].__setitem__(f, '0' * len(mod.LINEAGE[f])), True)
        for name, mutation in [
            ('source-only', lambda s: s['contract'].update(source_only=True)),
            ('synthetic-receipt-origin', lambda s: s['contract'].update(measurement_origin='source-review')),
            ('source-descriptor', lambda s: s['contract'].update(source_descriptor_sha256='0'*64)),
            ('empty-required', lambda s: s['contract'].update(required_members=[])),
            ('duplicate-required', lambda s: s['contract'].update(required_members=[2,2])),
            ('out-of-range-required', lambda s: s['contract'].update(required_members=[287])),
            ('bool-required', lambda s: s['contract'].update(required_members=[True])),
            ('dead-only-required', lambda s: s['contract'].update(required_members=[0])),
            ('missing-required', lambda s: s['contract'].update(required_members=[286])),
            ('wrong-arch', lambda s: s['contract'].update(architecture='arm64e')),
            ('guessed-option', lambda s: s['contract']['diagnostic_argv'].append('-invented')),
            ('missing-map-option', lambda s: s['document']['actual_link_argv'].__setitem__(-3,'-invalid')),
            ('wrong-output-operand', lambda s: s['document']['actual_link_argv'].__setitem__(2,'forged')),
            ('source-only-object-list', lambda s: s['document'].update(source_only=True)),
            ('missing-runtime', lambda s: s['document'].update(archives=[])),
            ('duplicate-runtime', lambda s: s['document']['archives'].append(s['document']['archives'][0])),
            ('wrong-member-hash', lambda s: s['document']['archives'][0]['members'][2].update(sha256='0'*64)),
            ('wrong-member-name', lambda s: s['document']['archives'][0]['members'][2].update(name='forged.o')),
            ('duplicate-member-ordinal', lambda s: s['document']['archives'][0]['members'][2].update(ordinal=1)),
            ('missing-member', lambda s: s['document']['archives'][0]['members'].pop()),
            ('unqualified-lto', lambda s: s['document'].update(lto_objects=[{'path':'lto.o','sha256':'0'*64,'source_argv_operand':str(archive)}])),
            ('forged-map-hash', lambda s: s.update(after_bind=lambda c: c['bindings']['map'].update(sha256='0'*64))),
            ('forged-map-path', lambda s: s.update(after_bind=lambda c: c['bindings']['map'].update(path='forged'))),
            ('image-view-hash', lambda s: s.update(view=lambda v: v.update(sha256='0'*64))),
            ('missing-final-provider', lambda s: s.update(view=lambda v: v.update(external_symbols={}))),
            ('wrong-final-provider-address', lambda s: s.update(view=lambda v: v.update(external_symbols={'___divtc3':{'undefined':False,'value':PC+8,'section':1,'type':15}}))),
        ]:
            case(name, mutation, True)
        def replace_line(index, value):
            return lambda state: state['rows'].__setitem__(index, value)
        for name, mutation in [
            ('missing-map', lambda s: s.update(rows=[])),
            ('wrong-path-header', replace_line(0, '# Path: forged')),
            ('duplicate-file-id', replace_line(5, '[  1] forged')),
            ('noncontiguous-file-id', replace_line(5, '[  9] forged')),
            ('foreign-member', replace_line(5, '[  2] /foreign/lib.a(member.o)')),
            ('unknown-symbol-file-id', replace_line(12, f'0x{PC+4:08X}\t0x00000004\t[999] ___divtc3')),
            ('unknown-dead-file-id', replace_line(16, '<<dead>> \t0x00000004\t[999] dead')),
            ('wrong-map-address', replace_line(12, f'0x{PC+8:08X}\t0x00000004\t[  2] ___divtc3')),
            ('atom-outside-section', replace_line(12, f'0x{PC+16:08X}\t0x00000004\t[  2] ___divtc3')),
            ('wrong-map-section', replace_line(8, f'0x{PC:08X}\t0x00000011\t__TEXT\t__text')),
            ('duplicate-map-section', lambda s: s['rows'].insert(9, s['rows'][8])),
            ('duplicate-provider', lambda s: s['rows'].insert(13, s['rows'][12])),
            ('only-noncatalog-live-label', replace_line(12, f'0x{PC+4:08X}\t0x00000004\t[  2] FDE for: ___divtc3')),
            ('archive-member-order', lambda s: s['rows'].__setitem__(slice(4,6),
                ['[  1] '+str(archive)+'('+catalog[2]['name']+')','[  2] '+str(archive)+'('+catalog[0]['name']+')'])),
            ('line-budget', replace_line(12, 'x'*65537)),
            ('nul-map', replace_line(12, '\0')),
            ('crlf-map', replace_line(12, '\r')),
            ('unknown-header', replace_line(10, '# invented format')),
        ]:
            case(name, mutation, True)
        def corrupt_archive(state):
            path = state['image'].parent / 'corrupt-runtime.a'
            with archive.open('rb') as src, path.open('wb') as dst:
                for block in iter(lambda: src.read(65536), b''):
                    dst.write(block)
            with path.open('r+b') as stream:
                stream.seek(-1, 2)
                byte = stream.read(1)
                stream.seek(-1, 2)
                stream.write(bytes([byte[0] ^ 1]))
            state['archive'] = path
        case('real-archive-byte-corruption', corrupt_archive, True)
        def corrupt_catalog(state):
            path = state['image'].parent / 'corrupt-catalog.json'
            value = json.loads(catalog_path.read_text())
            value[2]['sha256'] = '0'*64
            save(path, value)
            state['catalog'] = path
        case('real-catalog-byte-corruption', corrupt_catalog, True)
        # Optional source-derived stdout grammar, with no retention credit.
        diagnostic = args.out / 'synthetic-load-stdout.txt'
        diagnostic.write_text('___divtc3 forced load of '+str(archive)+'('+catalog[2]['name']+')\n')
        with core.CoherentFile(diagnostic) as snapshot:
            result = mod.parse_load_diagnostics(snapshot, str(archive), catalog)
        assert result['members'][0]['member_ordinal'] == 2 and not result['retention_credit']
        observations.append({'name':'synthetic-load-reason-only','outcome':'pass'})
        for name, content in [('diagnostic-unknown-member', str(archive)+'(unknown.o)'),
                              ('diagnostic-unknown-grammar', str(archive)+'('+catalog[2]['name']+')'),
                              ('diagnostic-duplicate', diagnostic.read_text().rstrip()+'\n'+diagnostic.read_text().rstrip())]:
            path = args.out / (name + '.txt')
            if name == 'diagnostic-unknown-member':
                content = 'forced load of ' + content
            path.write_text(content + '\n')
            try:
                with core.CoherentFile(path) as snapshot:
                    mod.parse_load_diagnostics(snapshot, str(archive), catalog)
            except ValueError as exc:
                observations.append({'name':name,'outcome':'pass','expected':'reject','reason':str(exc)})
            else:
                raise AssertionError('Expected diagnostic rejection: '+name)
        for name in ('fd-mutation', 'path-replacement', 'nofollow-symlink'):
            path = args.out / name
            path.write_bytes(b'owned control')
            try:
                if name == 'nofollow-symlink':
                    link = args.out / (name + '-link')
                    link.symlink_to(path)
                    with core.CoherentFile(link):
                        pass
                else:
                    with core.CoherentFile(path) as snapshot:
                        if name == 'fd-mutation':
                            path.write_bytes(b'mutated control')
                        else:
                            other = args.out / (name + '-new')
                            other.write_bytes(b'owned control')
                            other.replace(path)
                        snapshot.check()
            except (ValueError, OSError) as exc:
                observations.append({'name':name,'outcome':'pass','expected':'reject','reason':str(exc)})
            else:
                raise AssertionError('Expected coherent identity rejection: '+name)
        evidence.update(outcome='pass', summary=f'PASS {len(observations)} bounded runtime-map controls; genuine287 archive verified, synthetic maps/images confer no actual selection credit',
                        source_sha256=digest(source), core_source_sha256=digest(core_path),
                        control_source_sha256=digest(Path(__file__)),
                        source_descriptor_sha256=digest(descriptor_path),
                        runtime_archive_sha256=digest(archive), runtime_catalog_sha256=digest(catalog_path))
        exit_code = 0
    except BaseException as exc:
        evidence['failure'] = str(exc)
        (args.out / 'failure.txt').write_text(traceback.format_exc())
    finally:
        evidence.update(elapsed_seconds=time.monotonic()-started, mem_available_samples=samples,
                        vmhwm_bytes=next(int(line.split()[1])*1024 for line in
                        Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:')),
                        children_after=Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip())
        evidence['commands'][0]['exit_code'] = exit_code
        artifacts = sorted(p for p in args.out.rglob('*') if p.is_file() and not p.is_symlink())
        evidence['artifact_bindings'] = [{'path':str(p.relative_to(args.main)), 'sha256':digest(p)}
                                         for p in artifacts]
        evidence['artifacts'] = [str(p.relative_to(args.main)) for p in artifacts]
        save(args.out / 'evidence.json', evidence)
        print(json.dumps({'outcome':evidence['outcome'], 'controls':len(observations),
                          'vmhwm_bytes':evidence['vmhwm_bytes'], 'failure':evidence.get('failure'),
                          'evidence':str(args.out/'evidence.json')}))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
