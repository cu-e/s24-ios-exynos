#!/usr/bin/env python3
"""Read-only source audit of the genuine selected Scion guest crypto route."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'fixtures/public/avf-guest-crypto-route'
MANIFEST_HASH = 'afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd'


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bind(path, expected):
    actual = sha(path)
    require(actual == expected, 'Input hash mismatch: ' + str(path))
    return actual


def clean(text):
    # Preserve line numbers; the scanner is textual, not a C preprocessor.
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: '\n' * m[0].count('\n'), text, flags=re.S)


def parse(header, provider):
    body = clean(header).split('typedef struct crypto_functions {', 1)[1].split('}', 1)[0]
    fields = re.findall(r'\b(\w+)\s*;', body)
    require(len(fields) == 56 and len(set(fields)) == 56, 'Selected registration field set')
    table = provider.split('static struct crypto_functions mc_funcs = {', 1)[1].split('};', 1)[0]
    assignments = dict(re.findall(r'^\s*\.(\w+)\s*=\s*([^,\n]+)', table, re.M))
    require(len(assignments) == 34 and set(assignments) <= set(fields), 'Genuine static callback set')
    deferred = re.findall(r'mc_funcs\.(\w+)\s*=\s*(.*);', provider)
    require(deferred == [('ccsha256_di', 'mc_ce_sha256_di(ccsha256_di())')], 'Genuine deferred callback')
    require(re.search(r'STARTUP\(EARLY_BOOT, STARTUP_RANK_FIRST, minicrypto_init\)', provider), 'Provider startup rank')
    init = provider.split('minicrypto_init(void)', 1)[1]
    sequence = ['mc_digest_selftest()', 'mc_aes_selftest()', 'mc_ce_start()', 'mc_funcs.ccsha256_di =',
                'register_crypto_functions(&mc_funcs)', 'register_and_init_prng(']
    positions = [init.index(x) for x in sequence]
    require(positions == sorted(positions), 'Selftest/CE/SHA/publication/PRNG source order')
    return fields, assignments, deferred


def witness(path, text, pattern):
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(pattern, line):
            out.append({'source': path, 'line': number, 'text': line.strip()})
    return out


def audit(main, pins, output):
    graph_path = main / pins['graph']
    require(pins['graph_sha256'] == MANIFEST_HASH, 'Frozen guest graph identity')
    bind(graph_path, MANIFEST_HASH)
    graph = json.loads(graph_path.read_text())
    require(len(graph) == 1080 and len({r['id'] for r in graph}) == 1080, 'Exact guest object graph')
    original_path = main / pins['canonical_source_manifest']
    bind(original_path, pins['canonical_source_manifest_sha256'])
    original = json.loads(original_path.read_text())['scion']
    require(original['commit'] == pins['scion_commit'], 'Canonical Scion commit')
    origin = pins['provider_origin']
    canonical = next(r for r in original['files'] if r['path'] == origin['path'])
    require(canonical['oid'] == origin['git_blob_sha1'] and canonical['sha256'] == origin['sha256'],
            'Canonical provider Git blob and SHA256')
    source_root = main / pins['source_root']
    sources = {}
    for name, expected in pins['sources'].items():
        bind(source_root / name, expected)
        sources[name] = (source_root / name).read_text()
    separate = {name: bind(main / name, expected) for name, expected in pins['separate_route_inputs'].items()}
    provider_name = 'osfmk/minicrypto/mc_provider.c'
    header_name = 'libkern/libkern/crypto/register_crypto.h'
    fields, assignments, deferred = parse(sources[header_name], sources[provider_name])
    by_source = {}
    selected = []
    for row in graph:
        path = Path(row['bound_source'])
        bind(path, row['bound_source_sha256'])
        by_source.setdefault(str(path), []).append(row['id'])
        if '/minicrypto/' in str(path) or '/corecrypto/' in str(path) or row['id'] in {
                'osfmk/prng_random.o', 'osfmk/entropy.o', 'osfmk/startup.o', 'osfmk/vm_kern.o', 'libkern/register_crypto.o'}:
            configuration = Path(row['configuration'])
            bind(configuration, row['configuration_sha256'])
            selected.append({'id': row['id'], 'source': str(path.relative_to(source_root)),
                             'sha256': row['bound_source_sha256'], 'configuration': str(configuration.relative_to(main)),
                             'configuration_sha256': row['configuration_sha256'],
                             'compile_argv_template': row['next_owned_compile_argv_template'],
                             'status': 'source_recipe_bound_not_compiled_by_VM031'})
    required = {'osfmk/mc_provider.o', 'osfmk/mc_aes.o', 'osfmk/mc_ce.o', 'osfmk/mc_digests.o',
                'osfmk/mc_keywrap.o', 'osfmk/monocypher.o', 'osfmk/bearssl_aes_ct64.o',
                'osfmk/bearssl_aes_ct64_enc.o', 'osfmk/bearssl_aes_ct64_dec.o', 'libkern/register_crypto.o',
                'osfmk/prng_random.o', 'osfmk/entropy.o'}
    require(required <= {r['id'] for r in selected}, 'Genuine guest crypto object membership')
    scanned, demands = [], {f: [] for f in fields}
    for path in sorted(source_root.rglob('*')):
        if path.suffix not in ('.c', '.h', '.cpp') or not path.is_file():
            continue
        text = clean(path.read_text(errors='strict'))
        name = str(path.relative_to(source_root))
        scanned.append({'source': name, 'sha256': sha(path), 'selected_objects': by_source.get(str(path), [])})
        for match in re.finditer(r'\bg_crypto_funcs\s*->\s*(\w+)', text):
            field = match[1]
            require(field in demands, 'Unknown registration consumer field: ' + field)
            demands[field].append({'source': name, 'line': text[:match.start()].count('\n') + 1,
                                   'selected_objects': by_source.get(str(path), []),
                                   'source_sha256': scanned[-1]['sha256']})
    callbacks = []
    for ordinal, field in enumerate(fields):
        state = 'static_assignment' if field in assignments else 'unassigned_zero_by_C_static_initialization'
        expression = assignments.get(field)
        if field == deferred[0][0]:
            state, expression = 'assigned_before_registration', deferred[0][1]
        callbacks.append({'ordinal': ordinal, 'field': field, 'source_state': state,
                          'expression': expression, 'direct_text_demands': demands[field]})
    provider = sources[provider_name]
    body = sources['libkern/crypto/register_crypto.c']
    require('if (g_crypto_funcs)' in body and 'return -1;' in body and
            body.index('g_crypto_funcs = funcs;') < body.index('crypto_init = true;'), 'First registration body')
    startup = sources['osfmk/kern/startup.c']
    require('qsort(startup_entries, n, sizeof(struct startup_entry), startup_entry_cmp);' in startup and
            'a->rank > b->rank ? 1 : -1' in startup and 'cur->func(cur->arg);' in startup,
            'Actual startup sort and invocation')
    require('STARTUP(EARLY_BOOT, STARTUP_RANK_MIDDLE, kmem_crypto_init);' in sources['osfmk/vm/vm_kern.c'],
            'Actual kmem consumer rank')
    startup_witnesses = []
    patterns = {'osfmk/minicrypto/mc_provider.c': r'STARTUP\(|mc_.*selftest\(|mc_ce_start\(|mc_funcs.ccsha256|register_crypto|register_and_init|strictFIPS|initgen\(',
                'osfmk/kern/startup.c': r'a->rank|a->subsystem|qsort\(startup|cur->func|initialize_upto\(STARTUP_SUB_EARLY_BOOT',
                'osfmk/vm/vm_kern.c': r'crypto_random_kmem|STARTUP\(EARLY_BOOT',
                'osfmk/prng/prng_random.c': r'register_and_init_prng|entropy_init\(|init_with_getentropy|initgen\(|prng_ready =|cc_clear\(sizeof\(bootseed',
                'libkern/crypto/register_crypto.c': r'g_crypto_funcs|crypto_init'}
    for name, pattern in patterns.items():
        startup_witnesses.extend(witness(name, sources[name], pattern))
    # Real altered inputs stay in owned output; shared sources never change.
    controls = []
    bad_provider = output / 'reject-provider.c'
    bad_provider.write_text(provider.replace('STARTUP_RANK_FIRST, minicrypto_init', 'STARTUP_RANK_MIDDLE, minicrypto_init'))
    tests = [('changed-source-hash', lambda: bind(bad_provider, pins['sources'][provider_name])),
             ('changed-startup-rank', lambda: parse(sources[header_name], bad_provider.read_text())),
             ('removed-static-callback', lambda: parse(sources[header_name], provider.replace('.ccrng_fn = mc_ccrng,', ''))),
             ('changed-deferred-sha', lambda: parse(sources[header_name], provider.replace('mc_ce_sha256_di(ccsha256_di())', 'ccsha256_di()'))),
             ('reordered-publication', lambda: parse(sources[header_name], provider.replace('mc_ce_start();', '').replace('register_and_init_prng(', 'mc_ce_start(); register_and_init_prng(')))]
    for name, function in tests:
        try:
            function()
        except (ValueError, IndexError) as error:
            controls.append({'name': name, 'rejected': True, 'reason': str(error)})
        else:
            raise ValueError('Negative control accepted: ' + name)
    compiler_paths = {r['compile_argv_template'][0] for r in selected}
    compiler_pins = {p: sha(Path(p)) for p in compiler_paths}
    return {'task': 'VM-031', 'category': 'source-review', 'source_pins': pins,
            'selected_guest_object_count': len(graph), 'selected_source_rows_verified': len(graph),
            'crypto_and_startup_object_recipes': selected, 'compiler_files_hashed_not_executed': compiler_pins,
            'callback_count': len(callbacks), 'static_assignments': len(assignments), 'deferred_assignments': len(deferred),
            'unassigned_count': sum(c['source_state'].startswith('unassigned') for c in callbacks),
            'callbacks': callbacks, 'scanned_source_files': scanned,
            'scan_semantics': 'Comment-stripped direct g_crypto_funcs->field text; no preprocessor, call graph or runtime reachability proof. Selected object witnesses are source-recipe membership, never emitted symbols. Header/unselected references remain separately visible.',
            'startup_witnesses': startup_witnesses, 'separate_native_component_inputs': separate,
            'negative_controls': controls, 'boundaries': {'compiler_executed': False, 'linked_image': False,
            'guest_executed': False, 'native_E1S_objects_reused': False, 'provider_registered': False,
            'entropy_or_thread_safety_qualified': False, 'full_crypto_or_private_ABI_qualified': False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    report = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'fail',
              'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'argv': sys.argv, 'cwd': os.getcwd(), 'tool_sha256': sha(Path(__file__)),
              'python_sha256': sha(Path(sys.executable).resolve())}
    code = 1
    try:
        pins = json.loads((FIXTURE / 'inputs.json').read_text())
        report['audit'] = audit(args.main.resolve(), pins, args.out)
        report['outcome'] = 'pass'
        report['summary'] = 'Exact genuine guest crypto callback/source/object/startup route traced; no compile, link or execution qualification.'
        code = 0
    except Exception as error:
        report['summary'] = str(error)
        report['error_type'] = type(error).__name__
    report['elapsed_seconds'] = time.monotonic() - start
    report['exit_code'] = code
    report['current_image_memory'] = {line.split(':')[0]: line.split(':', 1)[1].strip()
        for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))}
    report['historical_inherited_ru_maxrss_kib_not_admission'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report['artifacts'] = [str((args.out / 'evidence.json').resolve())]
    (args.out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('outcome', 'summary', 'exit_code', 'elapsed_seconds', 'current_image_memory')}))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
