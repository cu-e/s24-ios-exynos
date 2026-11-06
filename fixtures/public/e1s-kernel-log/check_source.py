#!/usr/bin/env python3
"""STR034 source-only patch applicability and preserved-interface checks.

No C/assembly execution, compiler, full source preparation or target operations.
Only two copied source files in a new private artifact directory are patched.
"""
import argparse
import hashlib
import json
import re
import resource
import subprocess
import time
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    root = Path(__file__).resolve().parents[3]
    spec_path = Path(__file__).with_name('inputs.json')
    spec = json.loads(spec_path.read_bytes())
    patch = root / spec['patch']
    source = Path(spec['source_root'])
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    records, checks = [], []

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})
        if not condition:
            raise ValueError(name)

    def git(*argv, expected=0):
        command = [spec['git']['path'], *argv]
        result = subprocess.run(command, cwd=out, capture_output=True,
                                text=True, timeout=5)
        records.append({'argv': command, 'cwd': str(out),
                        'exit_code': result.returncode,
                        'stdout': result.stdout, 'stderr': result.stderr})
        check('git-' + '-'.join(argv[:2]),
              result.returncode == 0 if expected == 0 else result.returncode != 0)

    check('git-executable-pin', sha(spec['git']['path']) == spec['git']['sha256'])
    check('patch-pin', sha(patch) == spec['patch_sha256'])
    for path, expected in spec['inputs'].items():
        check('input-pin:' + path, sha(path) == expected)
    original = {}
    for name, pins in spec['files'].items():
        check('preimage:' + name, sha(source / name) == pins['before_sha256'])
        original[name] = (source / name).read_text()
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(original[name])
    # Own Git root is essential: a project-parent Git prefix can silently skip.
    git('init', '--quiet')
    git('apply', '--check', str(patch))
    git('apply', str(patch))
    for name, pins in spec['files'].items():
        check('postimage:' + name, sha(out / name) == pins['after_sha256'])
    git('apply', '--check', str(patch), expected=1)

    asm = (out / 'osfmk/arm64/start.s').read_text()
    old_asm = original['osfmk/arm64/start.s']
    log = (out / 'bsd/dev/e1s_log.c').read_text()
    old_log = original['bsd/dev/e1s_log.c']
    check('no-guessed-marker-address', '0x912f' not in asm and '#0xf000' not in asm)
    check('marker-initialized-writable-file-section',
          '\t.section __DATA,__data\n\t.align 3\nLe1s_boot_marker:\n'
          '\t.quad 0x4531534d41524b00\n\t.text\n' in asm)
    macro = asm.split('.macro E1S_BOOT_MARK n\n', 1)[1].split('.endm', 1)[0]
    check('marker-PC-relative-same-storage',
          'adrp\tx9, Le1s_boot_marker@page' in macro and
          'add\tx9, x9, Le1s_boot_marker@pageoff' in macro and
          'str\tx10, [x9]' in macro)
    check('marker-only-original-scratch-registers',
          set(re.findall(r'\bx\d+\b', macro)) == {'x9', 'x10'})
    check('four-original-marker-calls', re.findall(r'^\s+E1S_BOOT_MARK (\d+)$', asm, re.M)
          == re.findall(r'^\s+E1S_BOOT_MARK (\d+)$', old_asm, re.M) == ['1', '2', '3', '4'])
    check('all-marker-calls-before-MMU-enable',
          asm.index('E1S_BOOT_MARK 4') < asm.index('// Enable caches, MMU, ROP and JOP'))
    check('entry-MMU-exception-and-mapping-paths-unchanged',
          asm.split('\t.globl EXT(start_first_cpu)', 1)[1] ==
          old_asm.split('\t.globl EXT(start_first_cpu)', 1)[1])
    check('ring-has-no-fixed-PA-or-MMIO',
          all(token not in log for token in ('ml_io_map', 'E1S_LOG_PA', '0x91300000', '0x91200000')))
    check('ring-image-storage-full-size',
          '#define E1S_LOG_SIZE        (1U << 20)' in log and
          'static uint8_t e1s_log_storage[E1S_LOG_SIZE] __attribute__((aligned(8)));' in log and
          '\te1s_log = e1s_log_storage;' in log)
    check('header-and-append-byte-identical',
          old_log.split('static void\n', 1)[1].split('\nvoid\ne1s_log_init', 1)[0] ==
          log.split('static void\n', 1)[1].split('\nvoid\ne1s_log_init', 1)[0])
    check('disable-argument-and-counter-reset-byte-identical',
          old_log.split('e1s_log_init(void)\n{', 1)[1].split('\te1s_log =', 1)[0] ==
          log.split('e1s_log_init(void)\n{', 1)[1].split('\te1s_log =', 1)[0])
    startup = (source / 'osfmk/kern/startup.c').read_text()
    check('ring-init-after-vm-bootstrap-existing-interface',
          startup.index('\tvm_mem_bootstrap();') < startup.index('\te1s_log_init();'))
    loader_path = next(p for p in spec['inputs'] if p.endswith('/source/shim/e1s-xnu/loader.c'))
    loader = Path(loader_path).read_text()
    check('loader-segment-file-and-virtual-size-bounds',
          's->file_size > s->vmsize' in loader and
          's->vmaddr - p->virt_base > win_size - s->vmsize' in loader)
    check('loader-copies-file-and-zeroes-entire-segment-tail',
          'copy(dst, payload_start + s->file_off, s->file_size);' in loader and
          'zero(dst + s->file_size, s->vmsize - s->file_size);' in loader and
          'clean(dst, dst + s->vmsize);' in loader)
    packer_path = next(p for p in spec['inputs'] if p.endswith('/tools/e1s/xnu/mkpayload.py'))
    packer = Path(packer_path).read_text()
    check('packer-retains-zerofill-vmsize-and-reserves-end',
          "segs = [s for s in m['segs'] if s['vmsize']]" in packer and
          "kernel_end = max(s['vmaddr'] + s['vmsize'] for s in segs)" in packer and
          "pieces = [(s['vmaddr'], s['vmsize'], buf[s['fileoff']:s['fileoff'] + s['filesize']]) for s in segs]" in packer)
    # A changed diagnostic preimage must not be patched as though it were pinned.
    (out / 'osfmk/arm64/start.s').write_text(old_asm.replace('#0x912f', '#0x913f'))
    (out / 'bsd/dev/e1s_log.c').write_text(old_log)
    git('apply', '--check', str(patch), expected=1)
    # Leave the genuine patched two-file witness inspectable, not the negative case.
    (out / 'osfmk/arm64/start.s').write_text(asm)
    (out / 'bsd/dev/e1s_log.c').write_text(log)
    for name, pins in spec['files'].items():
        check('original-source-still-identical:' + name,
              sha(source / name) == pins['before_sha256'])
        check('retained-postimage:' + name, sha(out / name) == pins['after_sha256'])
    report = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'pass',
              'checks': checks, 'commands': records,
              'elapsed_seconds': time.monotonic() - started,
              'self_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
              'max_child_rusage_rss_bytes': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss * 1024,
              'address_space_limit_bytes': 256 << 20,
              'resource_limit_note': 'RLIMIT_AS is address-space, not aggregate sampled RSS; no target resource qualification.',
              'patch_sha256': sha(patch), 'input_spec_sha256': sha(spec_path),
              'target_execution': False, 'full_source_modified': False,
              'final_linked_layout_and_hardware_qualified': False}
    (out / 'source-checks.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'outcome': 'pass', 'checks': len(checks), 'report': str(out / 'source-checks.json')}))


if __name__ == '__main__':
    main()
