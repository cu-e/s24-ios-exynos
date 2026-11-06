#!/usr/bin/env python3
"""Focused independent frozen-source review; never invoke the corpus scanner."""
import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time

FREEZE = '3d903f8173acf81dc8b2b21eb1b620c34567a38c'
QUALIFIER = '9fc0a5b3ced553d801481e5e1984b94d703daf89'
BASE = 'aac27cfbc0d71b34eda33ddf366c72427507ae0b'
TOOL_SHA = 'a50048f526c3fe9998495152a796e32e86eef14f8e32bd2f7267bdf076297e1f'
EVIDENCE_SHA = '8fb6d01fdb88653a9d3aebcd4ffadf6c7f425a0ea380de145f8d2a31651560e9'
ROUTE_SHA = '3ced96c0e643e45d6c468ef9fb7290b0e6971ca1414f49934ebadd71325e9218'
SCOPE = ['tools/build/avf_guest_crypto_route.py', 'fixtures/public/avf-guest-crypto-route', 'docs/procedures/avf-guest-crypto-route']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def code_text(text):
    """Replace comments and quoted literals with spaces while retaining newlines."""
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
    return token.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), text)


def block(text, marker):
    start = text.index('{', text.index(marker))
    depth = 1
    for i in range(start + 1, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if not depth:
            return text[start + 1:i]
    raise ValueError('Unclosed focused source block: ' + marker)


def run(args, report):
    def check(condition, name):
        if not condition:
            raise ValueError(name)
        report['checks'].append(name)

    producer = args.producer
    tool = producer / SCOPE[0]
    docs = producer / SCOPE[2]
    inputs_path = producer / SCOPE[1] / 'inputs.json'
    route_path = docs / 'runs/source-audit2/route.json'
    maintained = docs / 'evidence.json'
    for p, expected in [(tool, TOOL_SHA), (maintained, EVIDENCE_SHA), (route_path, ROUTE_SHA)]:
        check(sha(p) == expected, 'Frozen SHA ' + str(p))
    report['read_inputs'] = {str(p): sha(p) for p in [tool, maintained, route_path, inputs_path]}
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    def git(*argv):
        result = subprocess.run(['git', '-C', str(producer), *argv], env=env, capture_output=True, timeout=10, check=True)
        report['git_queries'].append({'argv': argv, 'exit_code': result.returncode, 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest()})
        return result.stdout
    check(git('rev-parse', 'HEAD').decode().strip() == FREEZE, 'Exact producer HEAD')
    check(hashlib.sha256(git('show', QUALIFIER + ':' + SCOPE[0])).hexdigest() == TOOL_SHA, 'Qualifier tool equals frozen tool')
    check(git('diff', '--name-only', QUALIFIER, FREEZE, '--', *SCOPE[:2]) == b'', 'No tested code/input changes after qualifier')
    ancestry = git('log', '--reverse', '--format=%H %P %s', BASE + '..' + FREEZE, '--', *SCOPE).decode().splitlines()
    check(len(ancestry) == 9, 'Nine scoped ancestry commits')
    report['scoped_ancestry'] = ancestry
    changed = git('diff', '--name-only', BASE, FREEZE).decode().splitlines()
    check(all(any(p == root or p.startswith(root + '/') for root in SCOPE) for p in changed), 'Producer changes confined to original three reservations')
    report['producer_changed_paths'] = changed
    pins = json.loads(inputs_path.read_text())
    route = json.loads(route_path.read_text())
    evidence = json.loads(maintained.read_text())
    check(sha(inputs_path) == evidence['inputs_sha256'] and evidence['source_qualifier_commit'] == QUALIFIER, 'Maintained evidence exact tested input/qualifier')
    for rel, expected in evidence['sha256'].items():
        check(sha(args.main / rel) == expected, 'Preserved producer artifact ' + rel)
    check(route['source_pins'] == pins, 'Route retains exact source pins')
    check(route['separate_native_component_inputs'] == pins['separate_route_inputs'], 'Separate native input receipts retained historically')
    root = args.main / pins['source_root']
    texts = {}
    for name, expected in pins['sources'].items():
        path = root / name
        check(sha(path) == expected, 'Focused source SHA ' + name)
        texts[name] = path.read_text(encoding='latin-1')
    provider = texts['osfmk/minicrypto/mc_provider.c']
    header = texts['libkern/libkern/crypto/register_crypto.h']
    raw = provider.encode('latin-1')
    check(hashlib.sha1(('blob ' + str(len(raw)) + '\0').encode() + raw).hexdigest() == pins['provider_origin']['git_blob_sha1'], 'Actual provider canonical Git blob identity')
    declarations = block(code_text(header), 'typedef struct crypto_functions')
    fields = [re.findall(r'\b[A-Za-z_]\w*\b', d)[-1] for d in declarations.split(';') if d.strip()]
    entries = []
    for line in block(code_text(provider), 'static struct crypto_functions mc_funcs').splitlines():
        if line.strip():
            m = re.fullmatch(r'\s*\.(\w+)\s*=\s*(.*?)\s*,\s*', line)
            check(m is not None, 'Independent designated initializer grammar')
            entries.append(m.groups())
    assigned = dict(entries)
    missing = set(fields) - set(assigned) - {'ccsha256_di'}
    unsupported = set('ccaes_xts_encrypt ccaes_xts_decrypt ccaes_gcm_encrypt ccaes_gcm_decrypt ccgcm_init_with_iv_fn ccgcm_inc_iv_fn ccchacha20poly1305_fns ccdes_ecb_encrypt ccdes_ecb_decrypt ccdes_cbc_encrypt ccdes_cbc_decrypt cctdes_ecb_encrypt cctdes_ecb_decrypt cctdes_cbc_encrypt cctdes_cbc_decrypt ccdes_key_is_weak_fn ccdes_key_set_odd_parity_fn ccpad_cts3_encrypt_fn ccpad_cts3_decrypt_fn ccrsa_make_pub_fn ccrsa_verify_pkcs1v15_fn'.split())
    check(len(fields) == len(set(fields)) == 56, 'Independent 56 unique declaration fields')
    check(len(entries) == len(assigned) == 34, 'Independent 34 unique static assignments')
    check(missing == unsupported and len(missing) == 21, 'Independent exact 21 unsupported static-zero fields')
    check(len(route['callbacks']) == 56, 'Exactly 56 retained callback rows')
    for i, callback in enumerate(route['callbacks']):
        field = fields[i]
        state = 'static_assignment' if field in assigned else 'assigned_before_registration' if field == 'ccsha256_di' else 'unassigned_zero_by_C_static_initialization'
        expression = assigned.get(field, 'mc_ce_sha256_di(ccsha256_di())' if field == 'ccsha256_di' else None)
        check(callback['field'] == field and callback['ordinal'] == i and callback['source_state'] == state and callback['expression'] == expression, 'Independent callback row ' + field)
    code = code_text(provider)
    init = block(code, 'minicrypto_init(void)')
    ordered = ['mc_digest_selftest()', 'mc_aes_selftest()', 'mc_ce_start()', 'mc_funcs.ccsha256_di =', 'register_crypto_functions(&mc_funcs)', 'register_and_init_prng(']
    offsets = [init.index(s) for s in ordered]
    check(offsets == sorted(offsets), 'Actual narrow init selftest/CE/SHA/publication/PRNG source sequence')
    check(re.search(r'if\s*\(register_crypto_functions\(&mc_funcs\)\s*!=\s*0\)\s*\{\s*return\s*;', init), 'Competing-provider branch returns before donor PRNG call')
    check('STARTUP(EARLY_BOOT, STARTUP_RANK_FIRST, minicrypto_init);' in code, 'Provider EARLY_BOOT FIRST')
    check('STARTUP(EARLY_BOOT, STARTUP_RANK_MIDDLE, kmem_crypto_init);' in code_text(texts['osfmk/vm/vm_kern.c']), 'Kmem EARLY_BOOT MIDDLE')
    ranks = code_text(texts['osfmk/kern/startup.h'])
    check(re.search(r'STARTUP_RANK_FIRST\s*=\s*0\s*,', ranks) and re.search(r'STARTUP_RANK_MIDDLE\s*=\s*0x7fffffff\s*,', ranks), 'Actual declared FIRST and MIDDLE rank values')
    startup = code_text(texts['osfmk/kern/startup.c'])
    for token in ['a->subsystem > b->subsystem ? 1 : -1', 'a->rank > b->rank ? 1 : -1', 'qsort(startup_entries, n, sizeof(struct startup_entry), startup_entry_cmp);', 'cur->func(cur->arg);']:
        check(token in startup, 'Actual startup sort/invoke ' + token)
    registration = block(code_text(texts['libkern/crypto/register_crypto.c']), 'register_crypto_functions(')
    check(re.search(r'if\s*\(g_crypto_funcs\)\s*\{\s*return -1;', registration), 'Existing provider rejects second registration')
    check(registration.index('g_crypto_funcs = funcs;') < registration.index('crypto_init = true;'), 'Retained pointer precedes publication flag')
    check(not block(code, 'mc_prng_initgen(').strip(), 'Genuine single-generator initgen has empty body')
    check('(void)ccdrbg_generate' in block(code, 'mc_prng_reseed(') and 'mc_prng.custom.strictFIPS = 0;' in code, 'Discarded reseed status and non-FIPS setting retained')
    prng = block(code_text(texts['osfmk/prng/prng_random.c']), 'register_and_init_prng(')
    order = [prng.index(s) for s in ['entropy_init();', 'prng_funcs.init_with_getentropy(', 'prng_funcs.initgen(', 'prng_ready = 1;', 'cc_clear(sizeof(bootseed)']]
    check(order == sorted(order), 'Actual entropy/init/initgen/ready/clear source order')
    graph_path = args.main / pins['graph']
    check(sha(graph_path) == pins['graph_sha256'], 'Frozen original-profile graph SHA')
    graph = json.loads(graph_path.read_text())
    by_id = {r['id']: r for r in graph}
    by_source = {}
    for row in graph:
        by_source.setdefault(row['bound_source'], []).append(row['id'])
    recipes = route['crypto_and_startup_object_recipes']
    check(len(graph) == len(by_id) == 1080 and len(recipes) == 32, 'Reuse complete source receipt and exact 32 reported recipes')
    for recipe in recipes:
        row = by_id[recipe['id']]
        check(recipe['compile_argv_template'] == row['next_owned_compile_argv_template'] and recipe['sha256'] == row['bound_source_sha256'] and recipe['configuration_sha256'] == row['configuration_sha256'], 'Exact frozen recipe ' + row['id'])
        check(str(root / recipe['source']) == row['bound_source'] and sha(Path(row['bound_source'])) == recipe['sha256'] and sha(Path(row['configuration'])) == recipe['configuration_sha256'], 'Focused recipe source/config bytes ' + row['id'])
    scanned = route['scanned_source_files']
    index = {r['source']: r for r in scanned}
    check(len(scanned) == len(index) == 3842 and all(Path(n).suffix in ['.c', '.h', '.cpp'] for n in index), 'Reused corpus receipt count/suffixes; no traversal')
    generated = [row for row in graph if row['generated_input']]
    outside = [row['id'] for row in generated if not Path(row['bound_source']).is_relative_to(root)]
    check(len(generated) == len(outside) == 55, 'All 55 generated source slots remain outside composed textual corpus')
    report['generated_source_slots_outside_corpus'] = outside
    demands = [(c['field'], w) for c in route['callbacks'] for w in c['direct_text_demands']]
    check(len(demands) == 89, 'Exactly 89 published textual demands')
    demand_cache = {}
    for field, w in demands:
        name = w['source']
        if name not in demand_cache:
            path = root / name
            check(sha(path) == index[name]['sha256'], 'Existing witness file SHA ' + name)
            demand_cache[name] = path.read_text(encoding='latin-1').splitlines()
        check(w['source_sha256'] == index[name]['sha256'] and w['selected_objects'] == by_source.get(str(root / name), []), 'Witness source/object membership ' + field)
        check(re.search(r'\bg_crypto_funcs\s*->\s*' + re.escape(field) + r'\b', demand_cache[name][w['line'] - 1]), 'Actual published witness line ' + field)
    report['reused_receipts'] = {'corpus_files': 3842, 'corpus_traversed_again': False, 'published_demand_count': len(demands), 'witness_files_read': len(demand_cache), 'recipes_checked': 32, 'all_1080_source_hashes_replayed': False, 'generated_sources_outside_corpus': True}
    report['independent_source_classification'] = {'fields': fields, 'static_assignments': assigned, 'deferred': {'ccsha256_di': 'mc_ce_sha256_di(ccsha256_di())'}, 'unsupported_static_zero': sorted(missing)}
    # Extract only narrow pure helpers. The production audit/main are not loaded.
    names = {'sha', 'require', 'bind', 'clean', 'source_text', 'parse'}
    tree = ast.parse(tool.read_text())
    selected = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    ns = {'hashlib': hashlib, 're': re}
    exec(compile(selected, str(tool), 'exec'), ns)
    report['extracted_helpers'] = sorted(names)
    report['production_audit_or_main_invoked'] = False
    def case(name, fn, rejects=False):
        try:
            result = fn()
        except (ValueError, IndexError, FileNotFoundError) as exc:
            check(rejects, 'Unexpected focused control rejection ' + name)
            report['controls'].append({'case': name, 'rejected': True, 'reason': str(exc)})
        else:
            check(not rejects, 'Expected focused control rejection ' + name)
            report['controls'].append({'case': name, 'rejected': False, 'observation': result})
    with tempfile.TemporaryDirectory(prefix='owned-control-', dir=args.out) as tmp:
        tmp = Path(tmp)
        copied = tmp / 'provider.c'
        copied.write_bytes(raw)
        case('exact-owned-copy-hash', lambda: ns['bind'](copied, pins['sources']['osfmk/minicrypto/mc_provider.c']))
        copied.write_bytes(raw + b'\n')
        case('changed-owned-copy-hash', lambda: ns['bind'](copied, pins['sources']['osfmk/minicrypto/mc_provider.c']), True)
        case('missing-owned-file', lambda: ns['bind'](tmp / 'missing.c', '0' * 64), True)
        latin = tmp / 'latin.c'; latin.write_bytes(b'/*\x80*/\nint token;\n')
        case('lossless-nonUTF8-roundtrip', lambda: ns['source_text'](latin).encode('latin-1') == latin.read_bytes())
        check(ns['source_text'](latin).encode('latin-1') == latin.read_bytes(), 'NonUTF8 bytes roundtrip without source rewriting')
        case('frozen-positive-parser', lambda: [len(x) for x in ns['parse'](header, provider)])
        case('duplicate-declaration-field', lambda: ns['parse'](header.replace('ccdigest_update_fn;', 'ccdigest_init_fn;', 1), provider), True)
        commented = '/* fake\ng_crypto_funcs->ccrsa_make_pub_fn; */\nreal();\n'
        case('comment-removal-line-preservation', lambda: ns['clean'](commented).count('\n') == commented.count('\n') and 'g_crypto_funcs' not in ns['clean'](commented))
        check(ns['clean'](commented).count('\n') == commented.count('\n') and 'g_crypto_funcs' not in ns['clean'](commented), 'Comments excluded without changing line count')
        inactive = '#if 0\ng_crypto_funcs->ccrsa_make_pub_fn;\n#endif\n'
        case('inactive-text-remains-textual', lambda: 'g_crypto_funcs->ccrsa_make_pub_fn' in ns['clean'](inactive))
        check('g_crypto_funcs->ccrsa_make_pub_fn' in ns['clean'](inactive), 'Inactive branch token is intentionally still textual')
        literal = 'const char *s = "g_crypto_funcs->ccrsa_make_pub_fn";\n'
        case('quoted-demand-remains-textual', lambda: 'g_crypto_funcs->ccrsa_make_pub_fn' in ns['clean'](literal))
        check('g_crypto_funcs->ccrsa_make_pub_fn' in ns['clean'](literal), 'Quoted literal token is a documented focused limitation')
        duplicate = provider.replace('.ccrng_fn = mc_ccrng,', '.ccrng_fn = mc_ccrng,\n .ccrng_fn = mc_ccrng,')
        case('unbound-duplicate-designator-parser-limit', lambda: [len(x) for x in ns['parse'](header, duplicate)])
        copied.write_text(duplicate, encoding='latin-1')
        case('duplicate-designator-still-rejected-by-source-pin', lambda: ns['bind'](copied, pins['sources']['osfmk/minicrypto/mc_provider.c']), True)
        report['temporary_control_hashes'] = {p.name: sha(p) for p in tmp.iterdir()}
    check(not list(args.out.glob('owned-control-*')), 'Temporary owned filesystem controls cleaned')
    check(sha(root / 'osfmk/minicrypto/mc_provider.c') == pins['sources']['osfmk/minicrypto/mc_provider.c'], 'Original provider remains byte-identical after controls')
    report['bounded_notes'] = ['The frozen snapshot has no blocking source/data mismatch.', 'The lexical reader does not exclude quoted C literals or inactive branches; textual counts are not live demands.', 'The standalone parser collapses duplicate designators; the actual audit requires exact source hashes first, so this is not a fixed-snapshot admission bypass.', 'No corpus completeness, generated-source/TU/extraction/reachability/registration runtime, entropy, security, FIPS or private ABI claim is added.']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main', type=Path, required=True)
    p.add_argument('--producer', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    assert args.out.resolve().is_relative_to(Path(__file__).resolve().parent / 'runs')
    args.out.mkdir(parents=True, exist_ok=False)
    report = {'kind': 'host-test', 'origin': 'local-host', 'task': 'REV-044', 'owner': 'codex-review-guest-crypto-20261106-ey', 'outcome': 'fail', 'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'argv': sys.orig_argv, 'cwd': os.getcwd(), 'implementation_sha256': sha(Path(__file__)), 'checks': [], 'controls': [], 'git_queries': [], 'compiler_or_guest_executed': False, 'producer_changed': False}
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024**2, 256 * 1024**2))
    def deadline(signum, frame):
        raise TimeoutError('Focused independent review exceeded 90 seconds')
    signal.signal(signal.SIGALRM, deadline); signal.alarm(90)
    started = time.monotonic(); code = 1
    try:
        report['admission_samples'] = []
        for i in range(3):
            line = next(x for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
            value = int(line.split()[1]) * 1024; report['admission_samples'].append({'mem_available_bytes': value, 'monotonic': time.monotonic()})
            if value < 4 * 1024**3:
                raise RuntimeError('Focused light review admission below 4GiB')
            if i != 2: time.sleep(1)
        run(args, report)
        report.update(outcome='pass', summary='Bounded independent source snapshot/witness/recipe and focused parser/tempFS review passed; no compile/corpus redo/runtime claim')
        code = 0
    except Exception as exc:
        report.update(error=repr(exc), summary='Focused review attempt retained without acceptance')
    finally:
        signal.alarm(0)
        report['elapsed_seconds'] = time.monotonic() - started
        report['current_image_memory'] = {line.split(':')[0]: line.split(':')[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmRSS:', 'VmHWM:'))}
        report['historical_ru_maxrss_kib_not_current_memory'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        report['exit_code'] = code
        report['artifacts'] = [str(Path(__file__).resolve())]
        (args.out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'elapsed_seconds', 'current_image_memory']}, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
