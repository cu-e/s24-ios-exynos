#!/usr/bin/env python3
"""Stage actual E1S C regression inputs and a finite command plan; never compile.

Commands in the plan require separate root resource admission. No new executor.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(root, main, out, cc, upstream_git):
    config_path = root / 'fixtures/public/e1s-loader-memory/upstream.json'
    config = json.loads(config_path.read_text())
    patch = root / config['patch']
    if sha(patch) != config['patch_sha256']:
        raise ValueError('Patch pin changed')
    if out.exists() or out.is_symlink() or out.parent.resolve() != out.parent:
        raise ValueError('Output must be fresh with literal existing parent')
    out.mkdir()
    witness = {'source': config, 'patch_sha256': sha(patch), 'sources': {}}
    for variant in ['original', 'patched']:
        directory = out / variant
        directory.mkdir()
        for relative, record in config['sources'].items():
            source = main / 'references/s24-port' / relative
            if sha(source) != record['original_sha256']:
                raise ValueError('Pinned reference body mismatch: ' + relative)
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            witness['sources'][relative] = record['original_sha256']
    commands = []
    for check in [True, False]:
        argv = ['git', 'apply'] + (['--check'] if check else []) + [str(patch)]
        p = subprocess.run(argv, cwd=out/'patched', capture_output=True, timeout=15)
        commands.append({'argv': argv, 'cwd': str(out/'patched'), 'exit_code': p.returncode,
                         'stdout': p.stdout.decode(), 'stderr': p.stderr.decode()})
        if p.returncode:
            (out/'preparation-commands.json').write_text(json.dumps(commands, indent=2)+'\n')
            raise ValueError('Exact attributed patch did not apply')
    for relative, record in config['sources'].items():
        wanted = record.get('patched_sha256', record['original_sha256'])
        if sha(out/'patched'/relative) != wanted:
            raise ValueError('Patched body pin changed: ' + relative)
        p = subprocess.run(['git', '--git-dir='+str(upstream_git), 'show',
                            config['compatible_revision']+':'+relative],
                           capture_output=True, timeout=15)
        commands.append({'argv': ['git', '--git-dir='+str(upstream_git), 'show',
                                  config['compatible_revision']+':'+relative],
                         'exit_code': p.returncode})
        if p.returncode or hashlib.sha256(p.stdout).hexdigest() != record['original_sha256']:
            raise ValueError('New official revision is not byte-compatible: ' + relative)
    for variant in ['original', 'patched']:
        directory = out / variant
        loader = (directory/'shim/e1s-xnu/loader.c').read_text()
        selected = loader[loader.index('#define MAX_RANGES'):loader.index('uint64_t loader_main(')]
        (directory/'selection.inc').write_text(selected)
        shutil.copyfile(root/'fixtures/public/e1s-loader-memory/controls.c', directory/'controls.c')
    patched = (out/'patched/shim/e1s-xnu/loader.c').read_text()
    if ('if (!choose_window(dtb, loader_image, loader_size,' not in patched or
            'return fail("incomplete or unusable DTB RAM map");' not in patched or
            'window fallback' in patched or 'win_base = p->phys_base' in patched):
        raise ValueError('Actual loader must return failure, never use payload RAM fallback')
    if patched.index('if (!fdt_validate(dtb))') > patched.index('log_init();'):
        raise ValueError('Structural validation must precede legacy FDT/MMIO paths')
    host = ['--target=x86_64-unknown-linux-gnu', '-std=c11', '-O1', '-g',
            '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-Wall', '-Wextra', '-Werror']
    flags = ['--target=aarch64-none-elf', '-O2', '-g0', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-pic', '-fno-zero-initialized-in-bss',
             '-mstrict-align', '-mgeneral-regs-only', '-Wall', '-Wextra']
    plan = []
    for variant in ['original', 'patched']:
        directory = out/variant
        plan.append({'id': variant+'-compile', 'argv': [str(cc), *host,
                     '-I'+str(directory/'shim/e1s-xnu'), '-I'+str(directory),
                     str(directory/'controls.c'), str(directory/'shim/e1s-xnu/fdt.c'),
                     '-o', str(directory/'controls')], 'cwd': str(directory)})
        plan.append({'id': variant+'-controls', 'argv': [str(directory/'controls')]+
                     (['--legacy'] if variant=='original' else []), 'cwd': str(directory)})
    for name in ['loader.c', 'fdt.c']:
        directory = out/'patched/shim/e1s-xnu'
        plan.append({'id': name+'-freestanding', 'argv': [str(cc), *flags, '-c',
                     str(directory/name), '-o', str(out/(name+'.aarch64.o'))], 'cwd': str(directory)})
    inputs = {str(path): sha(path) for path in out.rglob('*') if path.is_file()}
    inputs.update({str(cc): sha(cc), str(patch): sha(patch), str(config_path): sha(config_path),
                   str(Path(__file__).resolve()): sha(__file__)})
    record = {'schema': 'e1s-loader-memory-focused-plan-v1', 'task': 'STR-002',
              'owner': 'codex-e1s-memory-20261106-sr2', 'phase': 'planned-not-executed',
              'max_jobs': 1, 'max_owned_rss_bytes': 256*1024**2, 'child_timeout_seconds': 120,
              'whole_timeout_seconds': 600, 'sanitizer_requires_RSS_only_no_small_RLIMIT_AS': True,
              'hardware_or_target_execution': False, 'commands': plan, 'input_sha256': inputs,
              'source_witness': witness, 'preparation_commands': commands}
    (out/'plan.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps({'phase': record['phase'], 'plan': str(out/'plan.json'),
                      'sha256': sha(out/'plan.json'), 'commands': len(plan)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--cc', type=Path, required=True)
    p.add_argument('--upstream-git', type=Path, required=True)
    a = p.parse_args()
    prepare(Path(__file__).resolve().parents[2], a.main.resolve(), a.out.absolute(),
            a.cc.resolve(), a.upstream_git.resolve())


if __name__ == '__main__':
    main()
