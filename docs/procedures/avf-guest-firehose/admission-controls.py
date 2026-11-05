"""Exercise the actual guest-row predicate without regenerating source products."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
ORIGINAL = '76db6b216fcb03c0e2035d37760464acbaca89ca'
PRODUCER = ROOT / 'tools/build/avf_guest_firehose.py'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_builder():
    spec = importlib.util.spec_from_file_location('firehose_admission_under_test', PRODUCER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    started = time.monotonic()
    sys.dont_write_bytecode = True
    builder = load_builder()
    manifest = MAIN / builder.MANIFEST
    assert sha(manifest) == builder.MANIFEST_SHA256
    row = next(r for r in json.loads(manifest.read_text()) if r['id'] == 'bsd/subr_log.o')
    compiler = Path(row['next_owned_compile_argv_template'][0])
    builder.validate_guest_row(copy.deepcopy(row), MAIN, compiler)
    results = [dict(name='exact-selected-template', accepted=True)]
    mutations = [
        ('later-undef-development', ['-UDEVELOPMENT']),
        ('later-development-zero', ['-DDEVELOPMENT=0']),
        ('split-development-zero', ['-D', 'DEVELOPMENT=0']),
        ('later-undef-board', ['-UARM64_BOARD_CONFIG_BCM2837']),
        ('later-board-zero', ['-DARM64_BOARD_CONFIG_BCM2837=0']),
        ('later-native-board', ['-DARM64_BOARD_CONFIG_E1S']),
        ('later-allocator-disable', ['-DXNU_NO_TYPE_BUILTINS=1']),
        ('later-private-zero', ['-DXNU_KERNEL_PRIVATE=0']),
        ('later-target', ['-target', 'x86_64-apple-ios16.5']),
        ('later-include', ['-include', '/tmp/unreviewed-profile.h']),
        ('later-response-file', ['@/tmp/unreviewed-profile.args']),
    ]
    for name, extra in mutations:
        changed = copy.deepcopy(row)
        changed['next_owned_compile_argv_template'].extend(extra)
        try:
            builder.validate_guest_row(changed, MAIN, compiler)
        except ValueError as error:
            results.append(dict(name=name, rejected=True, appended_tokens=extra, diagnostic=str(error)))
        else:
            raise AssertionError('Mutation accepted: ' + name)
    for name, mutate in [
        ('remove-profile-flag', lambda a: a.remove('-DDEVELOPMENT')),
        ('reorder-existing-flags', lambda a: a.__setitem__(slice(1, 3), list(reversed(a[1:3])))),
        ('change-output-template', lambda a: a.__setitem__(a.index('-o') + 1, '/tmp/unowned.o')),
    ]:
        changed = copy.deepcopy(row)
        mutate(changed['next_owned_compile_argv_template'])
        try:
            builder.validate_guest_row(changed, MAIN, compiler)
        except ValueError as error:
            results.append(dict(name=name, rejected=True, diagnostic=str(error)))
        else:
            raise AssertionError('Mutation accepted: ' + name)
    # The original acceptance is preserved as an actual executable regression
    # reproduction against the unchanged original committed producer bytes.
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0')
    argv = ['git', 'show', ORIGINAL + ':tools/build/avf_guest_firehose.py']
    original = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, check=True)
    old = dict(__name__='original_firehose_predicate', __file__=str(PRODUCER))
    exec(compile(original.stdout, 'original-76db6b2-avf_guest_firehose.py', 'exec'), old)
    changed = copy.deepcopy(row)
    changed['next_owned_compile_argv_template'].append('-UDEVELOPMENT')
    old['validate_guest_row'](changed, MAIN, compiler)
    frozen_plan = ROOT / 'docs/procedures/avf-guest-firehose/preparation-session3/compile-plan.json'
    plan = json.loads(frozen_plan.read_text())
    assert sha(frozen_plan) == 'f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197'
    assert len(plan['recipes']) == 3
    capsule = dict(schema_version=1, task='VM-020', kind='host-test', origin='local-host',
        recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), outcome='pass',
        argv=sys.orig_argv, exit_code=0,
        elapsed_seconds=round(time.monotonic() - started, 3),
        producer=dict(path=str(PRODUCER), sha256=sha(PRODUCER)),
        controls=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)),
        source_manifest=dict(path=str(manifest), sha256=sha(manifest)),
        selected_guest_argv=dict(id=row['id'], token_count=len(row['next_owned_compile_argv_template']),
            canonical_encoding='ASCII JSON array, ensure_ascii=True, separators=(comma,colon)',
            sha256=builder.GUEST_ARGV_SHA256, allowed_template_mutations=[]),
        original_reproduction=dict(commit=ORIGINAL, command=argv, exit_code=original.returncode,
            producer_git_bytes_sha256=hashlib.sha256(original.stdout).hexdigest(),
            appended_tokens=['-UDEVELOPMENT'], original_predicate_accepted=True),
        controls_results=results,
        preserved_compile_plan=dict(path=str(frozen_plan), sha256=sha(frozen_plan),
            recipe_ids=[r['id'] for r in plan['recipes']], bytes_changed=False,
            future_output_substitution_policy='Only original -o/-MF @OWNED_OUTPUT@ values may be concretized by a separately accepted executor; every other token must remain exact'),
        proc_status=[line.strip() for line in Path('/proc/self/status').read_text().splitlines()
                     if line.startswith(('VmHWM:', 'VmRSS:'))],
        source_regenerated=False, compiler_executed=False, qemu_executed=False,
        device_executed=False, common_checks_executed=False,
        accepted_for_execution=False,
        limits=['Predicate controls only; no source or object matrix rebuilt',
                'Original source evidence and frozen compile plan remain unchanged',
                'Independent capsule recheck and accepted component executor required before execution'])
    print(json.dumps(capsule, indent=2))


if __name__ == '__main__':
    main()
