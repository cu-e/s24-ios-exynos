#!/usr/bin/env python3
"""REVMAIN-001 real-file source controls; no target tools or production grants."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR = MAIN / 'worktrees/vm-022-link-phase-20261106'
SOURCE = AUTHOR / 'tools/build/avf_guest_link_inputs.py'
SOURCE_SHA = '6061ab8717590b1db02ef8d404071ce3345d35eb4a987c2fed0b3d83301e3006'
OLD = MAIN / 'worktrees/vm-022-tail-cancellation-20261106/tools/build/avf_guest_link_inputs.py'
OLD_SHA = '99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060'
BASE = 0xfffffff007004000


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def macho(image=True, segment_name=b'__TEXT', section_segment=b'__TEXT',
          section_offset=0x400, stored=0x480, symbol_type=0xf, symbol_value=None):
    address = BASE if image else 0
    entry = address + 0x400
    segment = struct.pack('<II16s4Q4I', 25, 152, segment_name,
                          address, 0x4000, 0, stored, 7, 5, 1, 0)
    section = struct.pack('<16s16sQQ8I', b'__text', section_segment,
                          entry, 16, section_offset, 2, 0, 0, 0, 0, 0, 0)
    symtab = struct.pack('<6I', 2, 24, 0x500, 1, 0x510, 9)
    thread = bytearray(288) if image else bytearray()
    if image:
        struct.pack_into('<4I', thread, 0, 5, 288, 6, 68)
        struct.pack_into('<Q', thread, 16+32*8, entry)
    commands = segment + section + symtab + thread
    data = bytearray(0x600)
    data[:32] = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0,
                           2 if image else 1, 3 if image else 2, len(commands), 0, 0)
    data[32:32+len(commands)] = commands
    data[0x400:0x410] = bytes(range(16))
    struct.pack_into('<IBBHQ', data, 0x500, 1, symbol_type, 1, 0,
                     entry if symbol_value is None else symbol_value)
    data[0x510:0x519] = b'\0__start\0'
    return bytes(data)


def archive(members):
    data = bytearray(b'!<arch>\n')
    for name, body in [('__.SYMDEF', b'toc'), *members]:
        data += (name+'/').encode().ljust(16) + b'0'.ljust(12) + b'0'.ljust(6) + b'0'.ljust(6)
        data += b'100644'.ljust(8) + str(len(body)).encode().ljust(10) + b'`\n' + body
        if len(body) % 2:
            data += b'\n'
    return bytes(data)


def xnup(kernel, cmdline=b'-v avf_exit=1\0'):
    body = bytearray()
    for name, content in [(b'kernel', kernel), (b'cmdline', cmdline)]:
        body += struct.pack('<16sII', name, len(content), 0) + content + bytes(-len(content) % 16)
    body += bytes(24)
    return struct.pack('<II', 0x50554e58, len(body)) + body


class FixtureCommon:
    """Real same-byte JSON/paths; root allocator is an explicit stop sentinel."""
    def __init__(self):
        self.approval_calls = 0

    @staticmethod
    def canonical_output_path(path):
        return Path(path).resolve()

    @staticmethod
    def load_project(path, expected=None):
        if expected is not None and sha(path) != expected:
            raise ValueError('Fixture same-byte JSON mismatch')
        return json.loads(Path(path).read_text())

    def project_approval(self, *args, **kwargs):
        self.approval_calls += 1
        raise RuntimeError('REVIEW_ONLY_ROOT_APPROVAL_BOUNDARY_NO_GRANT')


def large_worker(out):
    resource.setrlimit(resource.RLIMIT_AS, (192*1024**2, 192*1024**2))
    mod = load(SOURCE, 'review_large')
    count = 700_000
    path = out / 'legal-count-symbols.o'
    symoff = 32 + 24
    stroff = symoff + count*16
    with path.open('wb') as stream:
        stream.write(struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 1, 1, 24, 0, 0))
        stream.write(struct.pack('<6I', 2, 24, symoff, count, stroff, 1+count*9))
        for low in range(0, count, 4096):
            stream.write(b''.join(struct.pack('<IBBHQ', 1+index*9, 3, 0, 0, index+1)
                                  for index in range(low, min(low+4096, count))))
        stream.write(b'\0')
        for low in range(0, count, 4096):
            stream.write(b''.join(('_%07d' % index).encode()+b'\0'
                                  for index in range(low, min(low+4096, count))))
    start = time.monotonic()
    try:
        result = mod.bounded_macho(path)
        outcome = dict(kind='accepted', symbols=len(result['external_symbols']))
    except Exception as error:
        outcome = dict(kind=type(error).__name__, error=str(error))
    outcome.update(file_size=path.stat().st_size, symbols=count,
                   address_space_limit_bytes=192*1024**2,
                   elapsed_seconds=time.monotonic()-start, current_image_memory=mod.proc_status())
    write(out / 'large-result.json', outcome)
    return 0


def run(out):
    assert sha(SOURCE) == SOURCE_SHA and sha(OLD) == OLD_SHA
    out.mkdir(parents=True, exist_ok=False)
    mod = load(SOURCE, 'review_mainlink')
    checks = []
    initial = mod.proc_status()
    fds_before = len(os.listdir('/proc/self/fd'))
    def check(name, predicate, detail=None):
        checks.append(dict(name=name, pass_=bool(predicate), detail=detail))

    def rejects(name, func):
        try:
            value = func()
        except (ValueError, OSError, struct.error, UnicodeError) as error:
            check(name, True, dict(type=type(error).__name__, error=str(error)))
        else:
            check(name, False, dict(incorrectly_accepted=value))

    def fixture(name, data):
        path = out / name
        path.write_bytes(data)
        return path

    old_tree, new_tree = ast.parse(OLD.read_text()), ast.parse(SOURCE.read_text())
    inherited = {node.name: node for node in old_tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name != 'main'}
    current = {node.name: node for node in new_tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}
    for name, node in inherited.items():
        check('inherited-AST-'+name, ast.dump(node) == ast.dump(current[name]))
    check('empty-reviewed-profile-allowlist', mod.LINK_PROFILE_PINS == {})
    rejects('empty-profile-refuses-before-corpus', lambda: mod.admission_inputs(
        {'schema': 'avf-guest-link-admission-v1', 'profile': {'manifest': {'sha256': 'fictional'}}}, {}, None))
    plans = {}
    for kind, digest in [('link-vectors-2','14e118cfecd90d16784008918f6601b8e688b4d64cb51b6ef622dad5e795ddca'),
                         ('xnup-vectors-2','ea084235af736e3bc7117a7faed49b02a01827ccbb1e84334a9c0851bdea5b08')]:
        path = AUTHOR / 'artifacts/avf-guest-link-inputs' / kind / 'execution-plan.json'
        check(kind+'-frozen-hash', sha(path) == digest)
        plans[kind] = json.loads(path.read_text())
    plan = plans['link-vectors-2']
    check('1080-ordered-unique-source-ids', len(plan['ordered_ids']) == len(set(plan['ordered_ids'])) == 1080)
    check('eight-filelist-source-vectors', len(plan['filelist_commands']) == 8)
    check('1083-archive-nonlto-exclusion', plan['archive_members'] == 1083 and plan['nonlto_outside_archive'])
    check('DEVELOPMENT-no-export-or-undefined-override', all(x not in plan['link_argv'] for x in ['-exported_symbols_list','-undefined']))
    check('actual-selected-runtime-measurement-required-before-pass',
          '-map' in plan['link_argv'], 'No linkmap collection; executor explicitly sets actual_selected_archive_member_imports_unmeasured=True on pass')
    check('final-linked-allocator-validation-required',
          any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and 'alloc' in n.func.id.lower()
              for n in ast.walk(current['execute_link_stage_reserved'])),
          'No final-linked allocator metadata/string/relocation validator is called; common.macho only hashes input OSData metadata sections')

    image = fixture('image.bin', macho())
    obj = fixture('object.bin', macho(False))
    view = mod.bounded_macho(image, image=True)
    check('real-file-image-baseline', view['entry'] == BASE+0x400 and view['sha256'] == sha(image))
    check('real-file-object-baseline', mod.bounded_macho(obj)['filetype'] == 1)
    rejects('object-cannot-be-image', lambda: mod.bounded_macho(obj, image=True))
    rejects('truncated-header', lambda: mod.bounded_macho(fixture('short', b'X')))
    rejects('wrong-image-symbol-value', lambda: mod.bounded_macho(fixture('wrong-entry', macho(symbol_value=BASE+0x404)), image=True))
    rejects('image-section-parent-segment-name', lambda: mod.bounded_macho(fixture('bad-segname', macho(section_segment=b'__DATA')), image=True))
    rejects('image-section-file-bytes-inside-parent', lambda: mod.bounded_macho(fixture('bad-file-span', macho(section_offset=0x580)), image=True))
    rejects('image-section-file-to-VM-mapping', lambda: mod.bounded_macho(fixture('bad-mapping', macho(section_offset=0x420)), image=True))

    replacement = fixture('replacement.bin', b'not-a-Mach-O-but-real-bytes')
    victim = fixture('hash-swap-image', macho())
    real_sha = mod.sha
    swaps = []
    def swapping_sha(path):
        if Path(path) == victim and not swaps:
            os.replace(replacement, victim)
            swaps.append(dict(path=str(victim), action='actual os.replace after parse before real hash'))
        return real_sha(path)
    mod.sha = swapping_sha
    try:
        result = mod.bounded_macho(victim, image=True)
        check('parsed-image-and-returned-hash-same-bytes',
              not (swaps and result['sha256'] == sha(victim) and result['file_size'] != victim.stat().st_size),
              dict(returned=result, actual_path_size=victim.stat().st_size, mutation=swaps, reads_bypassed=False))
    finally:
        mod.sha = real_sha

    transformed = fixture('transformed.bin', obj.read_bytes())
    check('actual-transform-unchanged-baseline', mod.verify_segment_processing(obj, transformed, []) == [])
    real_open, mutations = Path.open, []
    def mutating_open(path, mode='r', *args, **kwargs):
        if path == transformed and mode == 'rb' and not mutations:
            with real_open(path, 'ab') as target:
                target.write(b'UNVALIDATED-TRAILER')
            mutations.append('actual append after size comparison before real result open/read')
        return real_open(path, mode, *args, **kwargs)
    Path.open = mutating_open
    try:
        try:
            result = mod.verify_segment_processing(obj, transformed, [])
            check('transform-post-stat-growth-refused', False,
                  dict(returned=result, mutation=mutations, original_size=obj.stat().st_size,
                       transformed_size=transformed.stat().st_size, reads_bypassed=False))
        except (ValueError, OSError) as error:
            check('transform-post-stat-growth-refused', bool(mutations), repr(error))
    finally:
        Path.open = real_open

    ar = fixture('members.a', archive([('a.o', b'one'), ('b.o', b'two!')]))
    check('archive-real-member-order-and-bytes', mod.stream_archive(ar) == [
        dict(name=name, sha256=hashlib.sha256(body).hexdigest(), file_size=len(body))
        for name,body in [('a.o',b'one'),('b.o',b'two!')]])
    rejects('archive-reject-truncation', lambda: mod.stream_archive(fixture('bad.a', ar.read_bytes()[:-1])))
    rejects('archive-reject-empty-members', lambda: mod.stream_archive(fixture('empty.a', archive([]))))
    payload = fixture('payload.xnup', xnup(image.read_bytes()))
    check('XNUP-real-ordered-byte-baseline', mod.inspect_xnup(payload, view)['entries'] == ['kernel','cmdline'])
    rejects('XNUP-reject-trailing-bytes', lambda: mod.inspect_xnup(fixture('trail.xnup', payload.read_bytes()+b'X'), view))
    rejects('XNUP-reject-changed-image', lambda: mod.inspect_xnup(fixture('changed.xnup', xnup(b'bad')), view))
    rejects('XNUP-reject-command-line', lambda: mod.inspect_xnup(fixture('cmd.xnup', xnup(image.read_bytes(), b'fake\0')), view))
    replacement = fixture('payload-replacement', b'not-an-XNUP')
    victim = fixture('hash-swap-payload', payload.read_bytes())
    swaps = []
    mod.sha = swapping_sha
    try:
        result = mod.inspect_xnup(victim, view)
        check('parsed-XNUP-and-returned-hash-same-bytes',
              not (swaps and result['sha256'] == sha(victim) and result['file_size'] != victim.stat().st_size),
              dict(returned=result, actual_path_size=victim.stat().st_size, mutation=swaps, reads_bypassed=False))
    finally:
        mod.sha = real_sha

    # Deliberately fictional package admission: real files, real hashing and actual
    # caller predicates, but no budget constructor/reservation/production grant.
    common = FixtureCommon()
    root = out / 'fixture-main'
    old_plan = root / 'worktrees/vm-022-20261106/artifacts/avf-guest-link-inputs/link-plan-2/final-link-execution-plan.json'
    old_plan.parent.mkdir(parents=True)
    old_plan.write_bytes((MAIN / old_plan.relative_to(root)).read_bytes())
    ledger = root / 'state/lab.json'
    ledger.parent.mkdir()
    write(ledger, dict(tasks=[dict(id='VM-022',owner=mod.OWNER,status='in_progress',worktree=str(AUTHOR))],
                       experiments=[dict(id='FICTIONAL-NOT-A-GRANT',task='VM-022',owner=mod.OWNER,status='planned')]))
    linked = out / 'fictional-source-only-link.json'
    write(linked, dict(outcome='pass',schema='WRONG-SCHEMA',task='OTHER',source_only=True,
                       executor_sha256='not-the-link-executor',direct_link_command_started=False,
                       archive_command_started=False,image=dict(path=str(image),sha256=sha(image))))
    accepted = out / 'fictional-acceptance.json'
    write(accepted, dict(schema='avf-guest-link-acceptance-v1',outcome='pass',
                         accepted_evidence={str(linked):sha(linked)}, fixture_only=True))
    request = out / 'fictional-request.json'
    write(request, dict(schema='avf-guest-xnup-admission-v1',
                        link_evidence=dict(path=str(linked),sha256=sha(linked)),
                        acceptance=dict(path=str(accepted),sha256=sha(accepted))))
    args = SimpleNamespace(main=root,vm008=MAIN/'worktrees/vm-008-20261105',
                           out=AUTHOR/'artifacts/avf-guest-link-inputs/REV041-NEVER-CREATED',
                           admission=request,admission_sha256=sha(request),task='VM-022',owner=mod.OWNER,
                           shard='guest-link-xnup',experiment='FICTIONAL-NOT-A-GRANT')
    args.execute_out = args.out
    plan = mod.xnup_vectors(args, common)
    args.source_plan = out / 'fictional-source-plan.json'
    write(args.source_plan, plan)
    args.source_plan_sha256 = sha(args.source_plan)
    args.approval = out / 'fictional-no-root-grant.json'
    write(args.approval, dict(source_plan_sha256=args.source_plan_sha256,fixture_only=True))
    args.approval_sha256 = sha(args.approval)
    try:
        mod.execute_xnup(args, common)
    except Exception as error:
        check('XNUP-reject-source-only-wrong-producer-before-root-boundary',
              common.approval_calls == 0,
              dict(exception=repr(error), root_approval_boundary_reached=common.approval_calls,
                   actual_constructor_or_grant_used=False, fixture_only=True))
    else:
        check('XNUP-reject-source-only-wrong-producer-before-root-boundary', False)
    check('fixture-created-no-author-output', not args.out.exists())

    command = [sys.executable,'-s',str(Path(__file__).resolve()),'--large-worker','--out',str(out)]
    with (out/'large.stdout').open('wb') as stdout, (out/'large.stderr').open('wb') as stderr:
        start = time.monotonic()
        child = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=8)
    large = json.loads((out/'large-result.json').read_text()) if (out/'large-result.json').exists() else None
    check('legal-count-symbol-parser-bounded-within-review-limit',
          child.returncode == 0 and large and large['kind'] != 'MemoryError',
          dict(argv=command,exit_code=child.returncode,elapsed_seconds=time.monotonic()-start,result=large))
    check('no-file-descriptor-leak', fds_before == len(os.listdir('/proc/self/fd')))
    check('source-physically-unchanged-after-controls', sha(SOURCE) == SOURCE_SHA)
    result = dict(kind='independent-source-review',task='REV-041',experiment='REVMAIN-001',
                  outcome='pass' if all(item['pass_'] for item in checks) else 'fail',
                  source=dict(path=str(SOURCE),sha256=sha(SOURCE)),checks=checks,
                  failed=[x['name'] for x in checks if not x['pass_']],
                  initial_process=initial,final_process=mod.proc_status(),
                  no_target_tools=True,no_production_allocation=True,no_runtime_or_kernel_credit=True,
                  read_mock_or_bypass=False,review_script_sha256=sha(__file__),argv=sys.argv)
    result['artifacts_sha256'] = {str(path.relative_to(out)):sha(path) for path in sorted(out.rglob('*')) if path.is_file()}
    write(out/'evidence.json', result)
    print(json.dumps(dict(outcome=result['outcome'],checks=len(checks),failed=result['failed'],final_process=result['final_process']),indent=2))
    return 0 if result['outcome'] == 'pass' else 2


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--large-worker',action='store_true')
    args = parser.parse_args()
    raise SystemExit(large_worker(args.out) if args.large_worker else run(args.out.resolve()))
