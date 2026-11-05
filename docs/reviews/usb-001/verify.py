#!/usr/bin/env python3
"""Independent, bounded USB-001 review witness. No device access."""
import ctypes as C
from datetime import datetime, timezone
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import resource
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
IMPL = MAIN / 'worktrees/usb-001-20261105'
COMMIT = 'e1785878045751213cb1e8e49e42a364333ed496'
WITNESS = IMPL / 'artifacts/usb-readonly/host-session5'
OUT = HERE / 'local/independent-001'
CLANG = '/home/egor/.local/bin/clang'
OUT.mkdir(parents=True, exist_ok=False)
COMMANDS = []


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def rel(p):
    return str(p.relative_to(MAIN))


def run(args, label, cwd=IMPL, expected=0, env=None):
    args = list(map(str, args))
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=45)
    stdout, stderr = OUT / (label + '.stdout.txt'), OUT / (label + '.stderr.txt')
    stdout.write_bytes(p.stdout)
    stderr.write_bytes(p.stderr)
    COMMANDS.append(dict(argv=args, cwd=str(cwd), exit_code=p.returncode,
                         stdout=rel(stdout), stderr=rel(stderr)))
    assert p.returncode == expected, (label, p.returncode, p.stderr[-2000:])
    assert resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss < 1024 * 1024
    return p.stdout


def oracle(lib):
    class Window(C.Structure):
        _fields_ = [('cpu', C.c_size_t), ('bus', C.c_uint64),
                    ('size', C.c_size_t), ('bits', C.c_uint32)]
    assert C.sizeof(C.c_size_t) == 8
    lib.s24_usb_dma_slice.argtypes = [C.POINTER(Window), C.c_size_t, C.c_size_t,
                                    C.POINTER(C.c_uint64)]
    lib.s24_usb_dma_slice.restype = C.c_int
    count = valid = invalid = 0
    maximum = (1 << 64) - 1

    def check(cpu, bus, size, bits, address, length):
        nonlocal count, valid, invalid
        # Inclusive interval model in unbounded integers, independent of the
        # implementation's subtraction-based overflow admission.
        end_cpu, end_bus = cpu + size - 1, bus + size - 1
        expected = (0 < bits <= 64 and size > 0 and length > 0 and
                    end_cpu <= maximum and end_bus < (1 << bits) and
                    cpu <= address and address + length - 1 <= end_cpu)
        output = C.c_uint64(0xDEADBEEF)
        w = Window(cpu, bus, size, bits)
        result = lib.s24_usb_dma_slice(C.byref(w), address, length, C.byref(output))
        assert (result == 0) == expected, (cpu, bus, size, bits, address, length, result)
        assert output.value == (bus + address - cpu if expected else 0xDEADBEEF)
        count += 1
        valid += expected
        invalid += not expected

    points = [0, 1, 4095, 4096, (1 << 36) - 1, 1 << 36,
              maximum - 4095, maximum - 1, maximum]
    sizes = [0, 1, 2, 4096, maximum]
    for cpu, bus, size, bits in itertools.product(points, points, sizes, [0, 1, 35, 36, 63, 64, 65]):
        for address in {(cpu - 1) & maximum, cpu, (cpu + 1) & maximum,
                        (cpu + size - 1) & maximum, (cpu + size) & maximum}:
            for length in sizes:
                check(cpu, bus, size, bits, address, length)
    rng = random.Random(0x555342)
    for _ in range(10000):
        bits = rng.choice([1, 32, 36, 48, 63, 64])
        size = rng.randrange(1, 65537)
        cpu = rng.randrange(maximum - size + 1)
        bus = rng.randrange(max(1, (1 << bits) - size + 1))
        address = cpu + rng.randrange(size + 2)
        length = rng.randrange(1, size + 2)
        check(cpu, bus, size, bits, address, length)
    return dict(cases=count, admitted=valid, rejected=invalid, mismatches=0,
                seed='0x555342', method='arbitrary-precision inclusive interval oracle')


report = dict(kind='source-review', origin='local-host', outcome='fail',
              recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
              commit=COMMIT, commands=COMMANDS,
              summary='Independent USB-001 review witness; no hardware/Apple qualification')
try:
    assert run(['git', 'rev-parse', 'HEAD'], 'implementation-head').decode().strip() == COMMIT
    assert not run(['git', 'status', '--porcelain'], 'implementation-status')
    report['review_base_commit'] = run(['git', 'rev-parse', 'HEAD'], 'review-head', HERE).decode().strip()
    run([CLANG, '--version'], 'compiler-version')
    run([CLANG, '-print-resource-dir'], 'compiler-resource')
    snapshot = OUT / 'source'
    snapshot.mkdir()
    executable_files = ['readonly.c', 'readonly.h', 'fixture.c', 'sanitizer-control.c', 'check.py', 'layout.cpp', 'profile.json']
    for i, name in enumerate(executable_files):
        content = run(['git', 'show', COMMIT + ':src/platform/usb/' + name], 'source-' + str(i))
        (snapshot / name).write_bytes(content)
        assert content == (WITNESS / 'source' / name).read_bytes()
    report['exact_snapshot_files'] = executable_files
    old = json.loads((WITNESS / 'evidence.json').read_text())
    for name, expected_hash in old['sha256'].items():
        assert digest(MAIN / name) == expected_hash, name
    summary = json.loads((IMPL / 'docs/procedures/usb-001/evidence-summary.json').read_text())
    for name, expected_hash in summary['evidence'].items():
        assert digest(MAIN / name) == expected_hash, name
    report['existing_witness_hashes_verified'] = len(old['sha256'])
    sources = json.loads((WITNESS / 'source-review.json').read_text())
    for label in ['reference', 'comparison']:
        pin = sources[label]
        repo = MAIN / pin['repository']
        assert run(['git', 'rev-parse', 'HEAD'], label + '-pin', repo).decode().strip() == pin['revision']
        for i, (name, facts) in enumerate(pin['files'].items()):
            data = run(['git', 'show', pin['revision'] + ':' + name], label + '-donor-' + str(i), repo)
            assert hashlib.sha256(data).hexdigest() == facts['sha256']
            assert len(data) == facts['bytes']
    report['pinned_donor_files_verified'] = 18
    flags = ['-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-O1', '-g', '-fno-omit-frame-pointer']
    sanitizer = ['-fsanitize=address,undefined']
    fixture, control = OUT / 'fixture', OUT / 'control'
    run([CLANG, *flags, *sanitizer, snapshot / 'readonly.c', snapshot / 'fixture.c', '-o', fixture], 'fixture-build')
    image = OUT / 'image'
    image.write_bytes(bytes(i % 251 for i in range(131072)))
    before = digest(image)
    env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
    result = json.loads(run([fixture, image], 'fixture-run', env=env))
    assert result['outcome'] == 'pass' and result['checks'] == 63482
    assert result['mutation_inputs'] == 20000 and digest(image) == before
    report['reproduced_fixture'] = result
    report['readonly_image_unchanged'] = True
    run([CLANG, *flags, *sanitizer, snapshot / 'sanitizer-control.c', '-o', control], 'control-build')
    for name, diagnostic in [('asan', b'AddressSanitizer: heap-buffer-overflow'), ('ubsan', b'runtime error: signed integer overflow')]:
        run([control, name], 'negative-' + name, expected=1, env=env)
        assert diagnostic in (OUT / ('negative-' + name + '.stderr.txt')).read_bytes()
    report['sanitizer_fault_controls'] = dict(asan='actual expected diagnostic, exit 1', ubsan='actual expected diagnostic, exit 1')
    library = OUT / 'readonly.so'
    run([CLANG, *flags, '-shared', '-fPIC', snapshot / 'readonly.c', '-o', library], 'oracle-library-build')
    report['independent_DMA_oracle'] = oracle(C.CDLL(str(library)))
    report['peak_child_RSS_KiB'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    report['outcome'] = 'pass'
except Exception as error:
    report['error'] = repr(error)
finally:
    report['artifacts'] = [rel(p) for p in sorted(OUT.rglob('*')) if p.is_file()]
    report['sha256'] = {rel(p): digest(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    report['limitations'] = ['Serialized host state only; trusted bounded backend and independent state storage required.',
                             'No phone, USB enumeration, PHY, hardware DMA, kernel/framework or Apple ABI qualification.',
                             'ARM objects from original witness are hash-audited, not rerun or executed.']
    (HERE / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'existing_witness_hashes_verified', 'reproduced_fixture', 'independent_DMA_oracle', 'peak_child_RSS_KiB']}, indent=2))
raise SystemExit(0 if report['outcome'] == 'pass' else 1)
