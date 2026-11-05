#!/usr/bin/env python3
"""Source/provenance/interface audit only. Does not build or execute crypto."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import struct
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
FIX = WT / 'fixtures/public/crypto-candidates'
PINS = {'mbedtls': '068ff080b369adfac81509f9b57b2afabaf82dc5',
        'bearssl': '7bea48e5e850ab4cafbe68d3765cdaba13a86d6f'}
sys.dont_write_bytecode = True
sys.path.insert(0, str(WT / 'tools/build'))
from xnu_kernel_syscalls import ObjectData


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_bytes(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Provenance hash mismatch: ' + str(path))
    return data


def pin_check(candidate, value):
    if value != PINS[candidate]:
        raise ValueError('Candidate pin does not match reviewed full revision')


def clean(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def api_definition(api, source, header):
    symbol = re.escape(api['symbol'])
    if not re.search(r'\b' + symbol + r'\s*\(', clean(header)):
        raise ValueError('Missing actual API declaration: ' + api['symbol'])
    if not re.search(r'\b' + symbol + r'\s*\([^;{}]*\)\s*\{', clean(source), re.S):
        raise ValueError('Missing actual algorithm/API function body: ' + api['symbol'])


def mapping_check(candidate, mappings, required, apis):
    if len(mappings) != len(required) or {r['field'] for r in mappings} != set(required):
        raise ValueError('Candidate assessment omits or duplicates selected callbacks')
    for row in mappings:
        group = required[row['field']]['group']
        if group != row['group']:
            raise ValueError('Selected callback group drift')
        if row['foreign_context_cast_allowed'] or row['persistent_heap_context_without_free_allowed'] or row['drop_in_qualified']:
            raise ValueError('Unsupported context/lifetime/drop-in promotion')
        if candidate == 'mbedtls' and group == 'xts' and row['status'] != 'whole-unit-api-not-mutable-tweak':
            raise ValueError('Whole-data-unit XTS does not provide selected mutable-tweak split-block API')
        if candidate == 'bearssl' and group == 'chacha' and row['status'] != 'whole-message-api-not-streaming':
            raise ValueError('Whole-message AEAD does not supply selected ten-method streaming API')
        if not row['apis'] and row['status'] != 'missing-reviewed-api':
            raise ValueError('Empty API coverage must remain an explicit gap')
        if group == 'cts3' and row['apis']:
            raise ValueError('Neither reviewed backend provides selected generic CBC-CS3; XTS stealing is different')
        allowed = {'gcm'} if group == 'gcm_nonce_helpers' else {group}
        if candidate == 'mbedtls' and group == 'xts':
            allowed.add('aes_block')
        if candidate == 'bearssl' and group.startswith('tdes_'):
            allowed = {group.replace('tdes_', 'des_')}
        for name in row['apis']:
            if apis[name]['candidate'] != candidate or apis[name]['family'] not in allowed:
                raise ValueError('Wrong candidate/algorithm family for callback')


def parse_vectors(text, name):
    if Path(name).name.startswith('TCBCI'):
        raise ValueError('Interleaved CBCI is not ordinary CBC')
    records, row, direction = [], {}, None

    def flush():
        if not row:
            return
        if direction not in ['ENCRYPT', 'DECRYPT']:
            raise ValueError('Vector direction missing')
        if 'KEYs' in row:
            part = bytes.fromhex(row['KEYs'])
            if len(part) != 8:
                raise ValueError('Invalid repeated DES key')
            key = part * 3
        else:
            parts = [bytes.fromhex(row[n]) for n in ['KEY1', 'KEY2', 'KEY3']]
            if any(len(part) != 8 for part in parts):
                raise ValueError('Invalid individual TDES key component')
            key = b''.join(parts)
        plain, cipher = bytes.fromhex(row['PLAINTEXT']), bytes.fromhex(row['CIPHERTEXT'])
        if len(key) != 24 or len(plain) != len(cipher) or not plain or len(plain) % 8:
            raise ValueError('Invalid TDES block/key/length vector')
        iv = bytes.fromhex(row['IV']) if Path(name).name.startswith('TCBC') else b''
        if iv and len(iv) != 8:
            raise ValueError('Invalid CBC vector IV')
        if Path(name).name.startswith('TCBC') and len(iv) != 8:
            raise ValueError('CBC vector IV missing')
        records.append(dict(direction=direction, count=int(row['COUNT']), key=key.hex(),
                            plaintext=plain.hex(), ciphertext=cipher.hex(), IV=iv.hex()))
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('['):
            flush(); row = {}; direction = line[1:-1]; continue
        key, value = [s.strip() for s in line.split('=', 1)]
        if key == 'COUNT' and row:
            flush(); row = {}
        if key in row:
            raise ValueError('Duplicate vector property')
        row[key] = value
    flush()
    if not records:
        raise ValueError('No actual vectors parsed')
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--cache-root', type=Path, default=HERE / 'local')
    a = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', a.run):
        raise ValueError('Use a fresh canonical run')
    out = HERE / 'local' / a.run
    if out.resolve() != out:
        raise ValueError('Symlink output forbidden')
    out.mkdir(parents=True, exist_ok=False)
    cache = a.cache_root.resolve()
    if not cache.is_relative_to(HERE) or cache == HERE:
        raise ValueError('Source cache must remain in the owned tool directory')
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0'}
    report = dict(kind='source-review', origin='local-host', outcome='fail',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  summary='Attempted requirements/candidate provenance audit; failures retained',
                  commands=[], checks=[], source_inputs={}, algorithm_executed=False,
                  candidate_built=False, provider_qualified=False, FIPS_qualified=False,
                  apple_private_ABI_qualified=False, native_qualified=False)

    def rel(path):
        return str(path.relative_to(MAIN))

    def bind(path, expected=None):
        if expected:
            verified_bytes(path, expected)
        report['source_inputs'][rel(path)] = sha(path)
        return path

    def run(args, label, cwd=WT):
        args = list(map(str, args))
        r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=30)
        stdout, stderr = out / (label + '.stdout.txt'), out / (label + '.stderr.txt')
        stdout.write_bytes(r.stdout); stderr.write_bytes(r.stderr)
        report['commands'].append(dict(argv=args, cwd=str(cwd), exit_code=r.returncode,
                                       stdout=rel(stdout), stderr=rel(stderr)))
        if r.returncode:
            raise ValueError(label + ' failed: ' + r.stderr[-900:].decode(errors='replace'))
        if resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss > 256 * 1024:
            raise ValueError('Child exceeded256MiB RSS')
        return r.stdout

    def check(name, condition, **facts):
        report['checks'].append(dict(name=name, passed=bool(condition), **facts))
        if not condition:
            raise ValueError(name)

    def reject(name, fn):
        try:
            fn()
        except (ValueError, KeyError) as error:
            check(name, True, diagnostic=str(error))
        else:
            check(name, False)

    try:
        report['commit'] = run(['git', 'rev-parse', 'HEAD'], 'commit').decode().strip()
        shutil.copyfile(__file__, out / 'verifier.py')
        req = json.loads(bind(FIX / 'requirements.json').read_text())
        corpus = json.loads(bind(FIX / 'candidates.json').read_text())
        vector_inputs = json.loads(bind(FIX / 'vector-inputs.json').read_text())
        catalog = json.loads(bind(MAIN / req['catalog']['path'], req['catalog']['sha256']).read_text())
        missing = {row['field']: row for row in catalog['table']['fields'] if row['state'] == 'unsupported'}
        required = {row['field']: row for row in req['slots']}
        check('all21-actual-missing-callbacks-bound', len(required) == 21 and set(required) == set(missing))
        selected = {}
        for i, (name, facts) in enumerate(req['selected_headers'].items()):
            data = run(['git', '-C', MAIN / 'references/apple-xnu', 'show', req['xnu_revision'] + ':' + name], 'selected-header-' + str(i))
            check('pinned-selected-header-' + str(i), hashlib.sha256(data).hexdigest() == facts['sha256'])
            check('actual-selected-header-matches-pin-' + str(i), bind(MAIN / facts['prepared_source'], facts['sha256']).read_bytes() == data)
            selected[name] = data.decode()
        for i, (name, facts) in enumerate(req['selected_sources'].items()):
            data = run(['git', '-C', MAIN / 'references/apple-xnu', 'show', req['xnu_revision'] + ':' + name], 'selected-caller-' + str(i))
            check('pinned-selected-caller-' + str(i), hashlib.sha256(data).hexdigest() == facts['sha256'])
            check('actual-selected-caller-matches-pin-' + str(i), bind(MAIN / facts['prepared_source'], facts['sha256']).read_bytes() == data)
            selected[name] = data.decode()
        header = clean(selected['libkern/libkern/crypto/register_crypto.h'])
        for field, row in required.items():
            declaration = re.sub(r'\s+', '', row['selected_declaration'])
            check('actual-signature-and-demand-' + field, declaration in re.sub(r'\s+', '', header) and
                  row['offset'] == missing[field]['offset'] and row['direct_demand'] == catalog['consumer_references'][field])
            if row['selected_function_typedef']:
                check('actual-function-typedef-' + field, re.sub(r'\s+', '', row['selected_function_typedef']) in re.sub(r'\s+', '', header))
        for row in req['ChaCha_function_table']:
            check('actual-ChaCha-method-' + row['method'], re.sub(r'\s+', '', row['actual_signature']) in re.sub(r'\s+', '', header))
        layout = json.loads(bind(MAIN / req['layout_witness']['path'], req['layout_witness']['sha256']).read_text())
        for path, digest in layout['sha256'].items():
            bind(MAIN / path, digest)
        for path, digest in layout['dependency_hashes'].items():
            verified_bytes(Path(path), digest)
        check('genuine-single-compile-layout-witness', layout['outcome'] == 'pass' and layout['target_layout'] == req['target_layout'] and
              len(layout['commands']) == 1 and layout['commands'][0]['exit_code'] == 0 and layout['peak_child_RSS_KiB'] <= 256 * 1024)
        obj = MAIN / next(path for path in layout['artifacts'] if path.endswith('/layout.o'))
        values = ObjectData(obj).value('_candidate_requirements_layout', '<16Q')
        check('independent-actual-layout-object-decoding', list(values) == list(req['target_layout'].values()))
        report['selected_target_layout'] = req['target_layout']
        report['layout_witness'] = req['layout_witness']
        check('two-real-pinned-backends', set(corpus['candidates']) == set(PINS))
        check('no-backend-or-private-runtime-promotion', not corpus['provider_qualified'] and
              not corpus['candidate_sizes_measured'] and not corpus['compiler_runtime_is_crypto_backend'] and
              all(not facts[key] for facts in corpus['candidates'].values()
                  for key in ['algorithm_executed', 'target_compiled', 'drop_in_qualified', 'native_qualified']))
        sources = {}
        for candidate, facts in corpus['candidates'].items():
            pin_check(candidate, facts['revision'])
            reject('reject-wrong-full-pin-' + candidate, lambda: pin_check(candidate, '0' * 40))
            for index, (name, evidence) in enumerate(facts['files'].items()):
                path = cache / candidate / name
                data = bind(path, evidence['sha256']).read_bytes()
                check('source-extent-' + candidate + '-' + str(index), len(data) == evidence['bytes'])
                if candidate == 'bearssl':
                    git_data = run(['git', '-C', cache / 'bearssl.git', 'show', facts['revision'] + ':' + name], 'bear-blob-' + str(index))
                    check('actual-primary-Git-blob-' + str(index), git_data == data)
                if name.endswith(('.c', '.h')):
                    notice = data[:3000].decode(errors='replace')
                    required_notice = 'SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later' if candidate == 'mbedtls' else 'Permission is hereby granted'
                    check('component-notice-' + candidate + '-' + str(index), required_notice in notice)
                sources[candidate + ':' + name] = data.decode()
            assessment = corpus['mappings'][candidate]
            mapping_check(candidate, assessment, required, corpus['api_evidence'])
            for omitted in required:
                reject('reject-assessment-omission-' + candidate + '-' + omitted,
                       lambda: mapping_check(candidate, [r for r in assessment if r['field'] != omitted], required, corpus['api_evidence']))
            sample = next(r for r in assessment if r['group'] == 'rsa_make')
            promoted = [{**r, 'persistent_heap_context_without_free_allowed': True} if r is sample else r for r in assessment]
            reject('reject-persistent-RSA-context-without-free-' + candidate, lambda: mapping_check(candidate, promoted, required, corpus['api_evidence']))
            cast = [{**r, 'foreign_context_cast_allowed': True} if r is sample else r for r in assessment]
            reject('reject-foreign-context-cast-' + candidate, lambda: mapping_check(candidate, cast, required, corpus['api_evidence']))
            if candidate == 'mbedtls':
                wrong = [{**r, 'status': 'direct-mutable-tweak-api'} if r['group'] == 'xts' else r for r in assessment]
                reject('reject-whole-unit-XTS-as-mutable-tweak', lambda: mapping_check(candidate, wrong, required, corpus['api_evidence']))
            else:
                wrong = [{**r, 'status': 'direct-streaming-api'} if r['group'] == 'chacha' else r for r in assessment]
                reject('reject-whole-message-ChaCha-as-streaming', lambda: mapping_check(candidate, wrong, required, corpus['api_evidence']))
            source_path = cache / candidate / next(name for name in facts['files'] if name.endswith('.c'))
            changed = out / (candidate + '-changed-source.c')
            changed.write_bytes(source_path.read_bytes() + b'\n/* provenance control */\n')
            reject('reject-actual-source-drift-' + candidate, lambda: verified_bytes(changed, sha(source_path)))
        for index, (key, api) in enumerate(corpus['api_evidence'].items()):
            api_definition(api, sources[api['candidate'] + ':' + api['source']], sources[api['candidate'] + ':' + api['header']])
            check('real-declaration-and-algorithm-body-' + str(index), True, symbol=api['symbol'], candidate=api['candidate'])
        for candidate in PINS:
            api = next(v for v in corpus['api_evidence'].values() if v['candidate'] == candidate)
            altered = sources[candidate + ':' + api['source']].replace(api['symbol'], 'removed_for_negative_control')
            reject('reject-missing-real-algorithm-body-' + candidate, lambda: api_definition(api, altered, sources[candidate + ':' + api['header']]))
        xts = 'mbedtls:mbedtls_aes_crypt_xts'
        wrong_cts = [{**r, 'status': 'real-source-needs-adapter', 'apis': [xts]} if r['group'] == 'cts3' else r for r in corpus['mappings']['mbedtls']]
        reject('reject-XTS-stealing-as-generic-CBC-CS3', lambda: mapping_check('mbedtls', wrong_cts, required, corpus['api_evidence']))
        # Confirm allocation/state facts against actual source, with explicit
        # configuration distinction; these tokens are not a full call graph.
        check('Mbed-RSA-public-verification-has-real-allocation', 'encoded          = mbedtls_calloc' in sources['mbedtls:library/rsa.c'] and 'encoded_expected = mbedtls_calloc' in sources['mbedtls:library/rsa.c'])
        check('Mbed-GCM-inline-vs-generic-paths-remain-distinct', '#if defined(MBEDTLS_BLOCK_CIPHER_C)' in sources['mbedtls:library/gcm.c'] and 'mbedtls_cipher_setup' in sources['mbedtls:library/gcm.c'] and 'union {' in sources['mbedtls:include/mbedtls/block_cipher.h'])
        check('Bear-RSA-view-ownership-is-explicit', 'unsigned char *n;' in sources['bearssl:inc/bearssl_rsa.h'] and 'unsigned char *e;' in sources['bearssl:inc/bearssl_rsa.h'] and 'uint32_t tmp[1 + TLEN]' in sources['bearssl:src/rsa/rsa_i31_pub.c'])
        check('selected-managed-GCM-nonce-contract-present', all(token in selected['EXTERNAL_HEADERS/corecrypto/ccmode.h']
              for token in ['IV must be exactly 12 bytes', 'four-byte salt followed by an eight-byte counter', 'big-endian, unsigned value']))
        xts_source = re.sub(r'\s+', '', sources['mbedtls:library/aes.c'])
        check('real-XTS-source-establishes-primitive-glue', all(token in xts_source for token in [
              'mbedtls_aes_crypt_ecb(&ctx->tweak,MBEDTLS_AES_ENCRYPT,data_unit,tweak)',
              'mbedtls_xor(tmp,input,tweak,16)', 'mbedtls_aes_crypt_ecb(&ctx->crypt,mode,tmp,tmp)',
              'mbedtls_xor(output,tmp,tweak,16)', 'mbedtls_gf128mul_x_ble(tweak,tweak)']))
        caller = re.sub(r'\s+', '', selected['libkern/crypto/corecrypto_aesxts.c'])
        check('selected-XTS-caller-return-handling-is-bounded-fact',
              'xtsenc->xts(xts->enc,tweak,ptlen/16,pt,ct);return0;' in caller and
              'xtsdec->xts(xts->dec,tweak,ptlen/16,ct,pt);return0;' in caller)
        report['vector_files'] = []
        all_cases = 0
        for archive in vector_inputs['archives']:
            zip_path = bind(cache / 'vectors' / archive['archive'], archive['archive_sha256'])
            with zipfile.ZipFile(zip_path) as z:
                for member in archive['members']:
                    path = bind(cache / 'vectors' / member['member'], member['sha256'])
                    check('actual-independent-vector-member-' + member['member'], z.read(member['member']) == path.read_bytes())
                    if Path(member['member']).name.startswith('TCBCI'):
                        report['vector_files'].append(dict(file=member['member'], excluded='interleaved CBCI is not normal CBC'))
                        continue
                    cases = parse_vectors(path.read_text(), member['member'])
                    all_cases += len(cases)
                    report['vector_files'].append(dict(file=member['member'], cases=len(cases), directions=sorted({c['direction'] for c in cases}), algorithm_executed=False))
        sample_path = cache / 'vectors/KAT_TDES/TECBvarkey.rsp'
        sample = sample_path.read_text()
        altered = re.sub(r'(CIPHERTEXT = )[0-9a-fA-F]+', r'\g<1>00', sample, count=1)
        reject('reject-real-vector-length-corruption', lambda: parse_vectors(altered, 'TECBvarkey.rsp'))
        reject('reject-interleaved-CBCI-as-normal-CBC', lambda: parse_vectors(sample, 'TCBCIinvperm.rsp'))
        check('independent-vectors-parsed-not-executed', all_cases > 0, cases=all_cases)
        report['independent_vector_cases'] = all_cases
        report['candidates'] = corpus['candidates']
        report['candidate_mappings'] = corpus['mappings']
        acquisition_paths = [cache / 'acquisition-git.json', cache / 'mbedtls/acquisition.json',
                             cache / 'mbedtls/initial-acquisition-failure.json', cache / 'bearssl/acquisition.json',
                             cache / 'vectors/failure.json', cache / 'vectors/provenance.json',
                             cache / 'vectors/mmt-provenance.json', cache / 'fetch-evidence.json']
        report['acquisition_history'] = []
        for path in acquisition_paths:
            if path.is_file():
                bind(path)
                report['acquisition_history'].append(dict(path=rel(path), sha256=sha(path)))
        report['qualifications'] = dict(source_provenance=True, requirements_coverage_assessed=True,
                                         selected_layout_measured=True, foreign_context_fit=False,
                                         backend_built=False, algorithm_executed=False, provider=False,
                                         FIPS=False, Apple_private_ABI=False, native=False)
        report['subprocess_environment'] = {k: env[k] for k in ['GIT_NO_LAZY_FETCH', 'GIT_OPTIONAL_LOCKS']}
        report['peak_verifier_child_RSS_KiB'] = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        report['outcome'] = 'pass'
        report['summary'] = 'Two genuine pinned candidates mapped to all21 missing callbacks with explicit API/lifetime/porting gaps; real source/provenance negatives and independent vector-data checks pass; no backend/provider or crypto runtime qualification'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        paths = [path for path in sorted(out.rglob('*')) if path.is_file()]
        report['artifacts'] = [rel(path) for path in paths]
        report['sha256'] = {rel(path): sha(path) for path in paths}
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'summary', 'independent_vector_cases', 'peak_verifier_child_RSS_KiB']}, indent=2))
    print('Source/data checks:', len(report['checks']))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
