#!/usr/bin/env python3
"""Audit historical candidate bytes against complete pinned public sources.

No network, compilation, upstream execution, extraction or shared writes.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

WT = Path(__file__).resolve().parents[3]
PINS = {'mbedtls': '068ff080b369adfac81509f9b57b2afabaf82dc5',
        'bearssl': '7bea48e5e850ab4cafbe68d3765cdaba13a86d6f'}
ARCHIVE_SHA = 'ca6bd316bbec49ef20088f39b8755fcaec0b7e45781506de55b17cd191ae6937'
ARCHIVE_ROOT = 'mbedtls-' + PINS['mbedtls']
OLD_COMMIT = '37c74737cc760602e9c392dccd1d67da13c48db8'
PATCH_PRE = 'adfd493f8ecb11f87f7e75f270a97cbd05d1902345ef32db51d39c076e4f8fde'
PATCH_POST = '3f7b4261ac2b7b429d0e7729aedeb4c26ad6a5e29d8878ad0437e68bbf4b2381'
INSERT = (b'/* Owned freestanding AES-only port: this unit uses no runtime assert. */\n'
          b'#if !defined(S24_XTS_FREESTANDING)\n#include <assert.h>\n#endif\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(data):
    return {'bytes': len(data), 'sha256': digest(data),
            'git_blob_sha1': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def dump(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def must(condition, message):
    if not condition:
        raise ValueError(message)


def stripped(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)


def body_extent(text, symbol):
    # Remove comments and literals without moving byte/line offsets. Braces in
    # diagnostics and character literals must not affect function extents.
    clean = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                   lambda m: re.sub(r'[^\n]', ' ', m[0]), text, flags=re.S)
    m = re.search(r'\b' + re.escape(symbol) + r'\s*\([^;{}]*\)\s*\{', clean, re.S)
    must(m is not None, 'Missing definition: ' + symbol)
    depth = 1
    for end in range(m.end(), len(clean)):
        depth += (clean[end] == '{') - (clean[end] == '}')
        if depth == 0:
            return m.start(), end + 1
    raise ValueError('Incomplete function body: ' + symbol)


def archive_check(data, revision):
    must(revision == PINS['mbedtls'], 'Wrong archive revision')
    must(digest(data) == ARCHIVE_SHA, 'Complete accepted official archive digest differs')


def line(text, pattern):
    m = re.search(pattern, text, re.S)
    must(m is not None, 'Source fact absent: ' + pattern)
    return text.count('\n', 0, m.start()) + 1


def apply_include_patch(base, diff):
    lines = diff.splitlines(keepends=True)
    must(lines[:2] == [b'--- a/library/common.h\n', b'+++ b/library/common.h\n'], 'Wrong patch member')
    must(len(lines) > 3, 'Missing patch hunk')
    match = re.fullmatch(rb'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n', lines[2])
    must(match is not None, 'Wrong patch hunk header')
    start, count, new_start, new_count = map(int, match.groups())
    must(start == new_start and all(s[:1] in [b' ', b'+', b'-'] for s in lines[3:]), 'Invalid patch hunk')
    before = [s[1:] for s in lines[3:] if s[:1] in [b' ', b'-']]
    after = [s[1:] for s in lines[3:] if s[:1] in [b' ', b'+']]
    original = base.splitlines(keepends=True)
    must(len(before) == count and len(after) == new_count and original[start-1:start-1+count] == before,
         'Patch hunk does not match exact canonical base')
    return b''.join(original[:start-1] + after + original[start-1+count:])


def patch(base, result, diff=None):
    must(digest(base) == PATCH_PRE, 'Patch base is not the complete canonical common.h')
    old = b'#include <assert.h>\n'
    must(base.count(old) == 1, 'Patch site is ambiguous')
    must(result == base.replace(old, INSERT) and digest(result) == PATCH_POST,
         'Patch result exceeds the accepted include-only transformation')
    if diff is not None:
        must(apply_include_patch(base, diff) == result, 'Actual patch artifact does not produce accepted bytes')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--main', type=Path, default=Path('/home/egor/dev/pet/s24-ios-exynos'))
    p.add_argument('--archive', type=Path)
    p.add_argument('--cache', type=Path)
    p.add_argument('--run', required=True)
    p.add_argument('--experiment', default='CRYSRC-001')
    p.add_argument('--publish', action='store_true', help='Write corrected manifests under the owned fixture path')
    a = p.parse_args()
    must(re.fullmatch(r'[A-Za-z0-9_-]+', a.run), 'Invalid run name')
    main_root = a.main.resolve()
    archive = a.archive or main_root / 'worktrees/krn-029-20261105/artifacts/crypto-xts/inputs/mbedtls.tar.gz'
    cache = a.cache or main_root / 'worktrees/krn-028-20261105/tools/research/crypto-candidates/local'
    out = WT / 'artifacts/crypto-source-integrity' / a.run
    out.mkdir(parents=True, exist_ok=False)
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0', 'PYTHONDONTWRITEBYTECODE': '1'}
    report = {'kind': 'source-review', 'origin': 'local-host', 'outcome': 'fail',
              'task': 'KRN-038', 'experiment': a.experiment,
              'owner': 'codex-team-crypto-source-integrity-20261105-bz',
              'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
              'commands': [], 'negative_controls': [], 'artifacts': {}, 'source_inputs': {},
              'algorithm_executed': False, 'compiler_executed': False, 'native_qualified': False}

    def run(argv):
        argv = list(map(str, argv))
        r = subprocess.run(argv, env=env, capture_output=True, timeout=30)
        n = len(report['commands'])
        for stream, data in [('stdout', r.stdout), ('stderr', r.stderr)]:
            name = f'command-{n:03d}.{stream}'
            (out / name).write_bytes(data)
            report['artifacts'][str((out / name).relative_to(WT))] = digest(data)
        report['commands'].append({'argv': argv, 'exit_code': r.returncode,
                                   'stdout_sha256': digest(r.stdout), 'stderr_sha256': digest(r.stderr)})
        must(r.returncode == 0, 'Read-only command failed: ' + repr(argv))
        return r.stdout

    def remember(path):
        data = path.read_bytes()
        report['source_inputs'][str(path)] = identity(data)
        return data

    def reject(name, fn, control):
        try:
            fn()
        except ValueError as error:
            report['negative_controls'].append({'name': name, 'outcome': 'pass',
                                                'rejection': str(error), 'input': control})
        else:
            raise ValueError('Negative control was accepted: ' + name)

    try:
        report['tested_commit'] = run(['git', '-C', WT, 'rev-parse', 'HEAD']).decode().strip()
        report['invocation'] = [sys.executable, *sys.argv]
        report['tool'] = identity(Path(__file__).read_bytes())
        report['python'] = {'executable': sys.executable, 'version': sys.version,
                            'executable_sha256': digest(Path(sys.executable).read_bytes())}
        report['git'] = {'executable': shutil.which('git'),
                         'executable_sha256': digest(Path(shutil.which('git')).read_bytes()),
                         'version': run(['git', '--version']).decode().strip()}
        catalog_path = WT / 'fixtures/public/crypto-candidates/candidates.json'
        catalog_bytes = remember(catalog_path)
        must(catalog_bytes == run(['git', '-C', main_root, 'show', OLD_COMMIT + ':fixtures/public/crypto-candidates/candidates.json']),
             'Historical catalog differs from the frozen KRN-028 commit')
        catalog = json.loads(catalog_bytes)
        remember(main_root / 'fixtures/public/crypto-candidates/qualified-audit.json')
        remember(cache / 'final-candidates-session1/evidence.json')
        remember(cache / 'mbedtls/acquisition.json')
        remember(cache / 'bearssl/acquisition.json')
        remember(cache / 'acquisition-git.json')
        archive_bytes = remember(archive)
        archive_check(archive_bytes, PINS['mbedtls'])
        provenance = json.loads(remember(WT / 'src/platform/crypto/xts/vendor/provenance.json'))
        must(provenance['commit'] == PINS['mbedtls'] and provenance['archive_sha256'] == ARCHIVE_SHA,
             'Independent accepted XTS archive binding differs')
        canonical = {}
        origins = {}
        with tarfile.open(archive, 'r:gz') as tar:
            members = tar.getmembers()
            must(all(PurePosixPath(m.name).parts[0] == ARCHIVE_ROOT for m in members), 'Archive root revision differs')
            names = [m.name for m in members]
            must(len(names) == len(set(names)), 'Ambiguous duplicate archive members')
            for name in catalog['candidates']['mbedtls']['files']:
                member = ARCHIVE_ROOT + '/' + name
                m = tar.getmember(member)
                must(m.isfile() and 0 < m.size <= 2 * 1024 * 1024, 'Nonregular or oversized canonical member')
                data = tar.extractfile(m).read()
                must(len(data) == m.size, 'Archive member extent differs')
                canonical['mbedtls', name] = data
                origins['mbedtls', name] = {'archive_sha256': ARCHIVE_SHA, 'member': member}
        repo = cache / 'bearssl.git'
        pin = PINS['bearssl']
        commit = run(['git', '-C', repo, 'cat-file', 'commit', pin])
        must(hashlib.sha1(b'commit ' + str(len(commit)).encode() + b'\0' + commit).hexdigest() == pin,
             'BearSSL commit object identity differs')
        real_parent = re.search(rb'^parent ([0-9a-f]{40})$', commit, re.M).group(1).decode()
        tree = run(['git', '-C', repo, 'ls-tree', '-r', pin]).decode()
        tree_rows = {}
        for row in tree.splitlines():
            meta, name = row.split('\t', 1)
            mode, kind, blob = meta.split()
            tree_rows[name] = (mode, kind, blob)
        for name in catalog['candidates']['bearssl']['files']:
            mode, kind, blob = tree_rows[name]
            must(kind == 'blob' and mode == '100644', 'Unexpected canonical BearSSL member type')
            data = run(['git', '-C', repo, 'cat-file', 'blob', pin + ':' + name])
            must(identity(data)['git_blob_sha1'] == blob, 'BearSSL tree/blob identity differs')
            canonical['bearssl', name] = data
            origins['bearssl', name] = {'commit': pin, 'tree_blob_sha1': blob, 'mode': mode}

        def verify(candidate, revision, name, data, member=None):
            must(revision == PINS[candidate], 'Wrong full revision')
            must((candidate, name) in canonical, 'Unreviewed member')
            if candidate == 'mbedtls':
                must(member == ARCHIVE_ROOT + '/' + name, 'Wrong archive member identity')
            must(data == canonical[candidate, name], 'Bytes differ from complete canonical member')

        corrected = {'schema_version': 1, 'kind': 'source-review', 'historical_task': 'KRN-028',
                     'historical_commit': OLD_COMMIT, 'historical_catalog_sha256': digest(catalog_bytes),
                     'canonical_mbed_archive_sha256': ARCHIVE_SHA, 'candidates': {}}
        discrepancies = []
        snapshots = {}
        for candidate, facts in catalog['candidates'].items():
            must(facts['revision'] == PINS[candidate], 'Catalog pin drift')
            result = corrected['candidates'][candidate] = {k: facts[k] for k in ['revision', 'repository', 'license']}
            result['files'] = {}
            for name, historical in facts['files'].items():
                cached = remember(cache / candidate / name)
                snapshots[cache / candidate / name] = digest(cached)
                data = canonical[candidate, name]
                full = identity(data)
                must(identity(cached)['sha256'] == historical['sha256'] and len(cached) == historical['bytes'],
                     'Historical cached bytes no longer match their immutable catalog')
                verify(candidate, facts['revision'], name, data, origins[candidate, name].get('member'))
                status = 'identical' if cached == data else ('strict-prefix-truncated' if data.startswith(cached) else 'different')
                row = {**full, 'origin': origins[candidate, name], 'historical': historical, 'comparison': status}
                if name.endswith(('.c', '.h')):
                    notice = 'SPDX-License-Identifier: Apache-2.0 OR GPL-2.0-or-later' if candidate == 'mbedtls' else 'Permission is hereby granted'
                    row['component_notice_line'] = line(data.decode(), re.escape(notice))
                result['files'][name] = row
                if status != 'identical':
                    suffix = data[len(cached):] if data.startswith(cached) else b''
                    discrepancy = {'candidate': candidate, 'path': name, 'comparison': status,
                                   'historical': identity(cached), 'canonical': full,
                                   'historical_last_line': cached.decode().splitlines()[-1],
                                   'historical_last_line_number': cached.count(b'\n') + 1,
                                   'canonical_line_count': data.count(b'\n'),
                                   'missing_bytes': len(data) - len(cached),
                                   'omitted_error_directives': [s for s in suffix.decode().splitlines() if s.lstrip().startswith('#error')],
                                   'named_api_evidence_using_file': [k for k, v in catalog['api_evidence'].items()
                                       if v['candidate'] == candidate and name in [v['source'], v['header']]]}
                    discrepancies.append(discrepancy)
        must(sum(len(v['files']) for v in corrected['candidates'].values()) == 67, 'Expected all 67 entries')
        api_facts = []
        for key, api in catalog['api_evidence'].items():
            body = canonical[api['candidate'], api['source']].decode()
            header = canonical[api['candidate'], api['header']].decode()
            symbol = re.escape(api['symbol'])
            start, end = body_extent(body, api['symbol'])
            old = (cache / api['candidate'] / api['source']).read_bytes()
            api_facts.append({'id': key, **api,
                              'definition_line': body.count('\n', 0, start) + 1,
                              'definition_end_line': body.count('\n', 0, end) + 1,
                              'entire_body_within_historical_prefix': old == body.encode() or (body.encode().startswith(old) and len(body[:end].encode()) <= len(old)),
                              'declaration_line': line(stripped(header), r'\b' + symbol + r'\s*\('),
                              'source_sha256': digest(body.encode()), 'header_sha256': digest(header.encode()),
                              'qualification': 'declaration/body presence only; no ABI, allocation closure or algorithm execution'})
        must(len(api_facts) == 44, 'Expected all 44 API facts')
        facts = []
        tokens = [
            ('mbedtls', 'library/aes.c', 'mbedtls_aes_crypt_ecb(&ctx->tweak, MBEDTLS_AES_ENCRYPT', 'XTS tweak key uses encryption'),
            ('mbedtls', 'library/aes.c', 'mbedtls_gf128mul_x_ble(tweak, tweak)', 'XTS mutable local tweak step'),
            ('mbedtls', 'library/gcm.c', '#if defined(MBEDTLS_BLOCK_CIPHER_C)', 'GCM configuration-dependent block cipher path'),
            ('mbedtls', 'library/gcm.c', 'mbedtls_cipher_setup', 'GCM generic cipher setup path exists'),
            ('mbedtls', 'include/mbedtls/block_cipher.h', 'union {', 'GCM block cipher context union'),
            ('mbedtls', 'library/rsa.c', 'encoded          = mbedtls_calloc', 'RSA verification allocation exists'),
            ('mbedtls', 'library/rsa.c', 'encoded_expected = mbedtls_calloc', 'RSA expected-encoding allocation exists'),
            ('bearssl', 'inc/bearssl_rsa.h', 'unsigned char *n;', 'RSA public modulus is a borrowed byte pointer'),
            ('bearssl', 'inc/bearssl_rsa.h', 'unsigned char *e;', 'RSA exponent is a borrowed byte pointer'),
            ('bearssl', 'src/rsa/rsa_i31_pub.c', 'uint32_t tmp[1 + TLEN]', 'RSA public operation local stack array')]
        for candidate, name, token, meaning in tokens:
            data = canonical[candidate, name]
            facts.append({'candidate': candidate, 'path': name, 'line': line(data.decode(), re.escape(token)),
                          'token': token, 'meaning': meaning, 'sha256': digest(data)})
        check_name = 'include/mbedtls/check_config.h'
        full = canonical['mbedtls', check_name]
        partial = (cache / 'mbedtls' / check_name).read_bytes()
        must(partial != full and full.startswith(partial), 'Expected real historical truncation is absent')
        reject('historical-truncation-with-matching-raw-hash',
               lambda: verify('mbedtls', PINS['mbedtls'], check_name, partial, ARCHIVE_ROOT + '/' + check_name),
               {**identity(partial), 'self_consistent_catalog_hash': digest(partial)})
        changed = full[:-1] + bytes([full[-1] ^ 1])
        reject('same-length-content-change-with-forged-raw-hash',
               lambda: verify('mbedtls', PINS['mbedtls'], check_name, changed, ARCHIVE_ROOT + '/' + check_name), identity(changed))
        reject('wrong-revision-with-identical-bytes',
               lambda: verify('mbedtls', '0' * 40, check_name, full, ARCHIVE_ROOT + '/' + check_name), {'revision': '0' * 40})
        reject('wrong-member-with-identical-bytes',
               lambda: verify('mbedtls', PINS['mbedtls'], check_name, full, ARCHIVE_ROOT + '/library/gcm.c'), {'member': ARCHIVE_ROOT + '/library/gcm.c'})
        reject('valid-other-member-content',
               lambda: verify('mbedtls', PINS['mbedtls'], check_name, canonical['mbedtls', 'library/gcm.c'], ARCHIVE_ROOT + '/' + check_name), identity(canonical['mbedtls', 'library/gcm.c']))
        reject('real-parent-revision-with-current-bytes', lambda: verify('bearssl', real_parent, 'LICENSE.txt', canonical['bearssl', 'LICENSE.txt']),
               {'revision': real_parent, 'identity_source': 'parent of the verified canonical commit object'})
        reject('truncated-bear-file', lambda: verify('bearssl', PINS['bearssl'], 'inc/bearssl_rsa.h', canonical['bearssl', 'inc/bearssl_rsa.h'][:-1]), {'removed_bytes': 1})
        reject('truncated-full-archive', lambda: archive_check(archive_bytes[:-1], PINS['mbedtls']), identity(archive_bytes[:-1]))
        reject('changed-archive-revision', lambda: archive_check(archive_bytes, '0' * 40), {'revision': '0' * 40})
        base = canonical['mbedtls', 'library/common.h']
        local = remember(WT / 'src/platform/crypto/xts/vendor/library/common.h')
        patch_artifact = remember(WT / 'src/platform/crypto/xts/vendor/common-freestanding.patch')
        patch(base, local, patch_artifact)
        reject('modified-patch-base', lambda: patch(base[:-1], local), identity(base[:-1]))
        reject('modified-patch-result', lambda: patch(base, local + b'\n'), identity(local + b'\n'))
        reject('unpatched-file-is-not-patched-result', lambda: patch(base, base), identity(base))
        wrong_member_patch = patch_artifact.replace(b'a/library/common.h', b'a/library/gcm.c')
        reject('wrong-patch-member', lambda: patch(base, local, wrong_member_patch), identity(wrong_member_patch))
        wrong_hunk_patch = patch_artifact.replace(b' #include "alignment.h"', b' #include "wrong_alignment.h"')
        reject('wrong-patch-base-context', lambda: patch(base, local, wrong_hunk_patch), identity(wrong_hunk_patch))
        patches = {'library/common.h': {'canonical_pre': identity(base), 'accepted_xts_post': identity(local),
                   'patch_artifact_sha256': digest(patch_artifact), 'transformation': 'exact named conditional around the single unused assert.h include',
                   'accepted_positive_control': True}}
        must(all(digest(path.read_bytes()) == expected for path, expected in snapshots.items()), 'Shared historical source was changed during audit')
        must(digest(archive.read_bytes()) == ARCHIVE_SHA, 'Shared accepted archive changed during audit')
        assessment = {'schema_version': 1, 'discrepancies': discrepancies, 'api_facts': api_facts,
                      'bridge_source_facts': facts, 'patches': patches,
                      'summary': {'named_files': 67, 'canonical_matches': 67 - len(discrepancies),
                                  'discrepancies': len(discrepancies), 'API_facts_reestablished': len(api_facts)},
                      'limits': ['Source identities and presence only; no compile, crypto execution, provider, FIPS, private Apple ABI or native qualification.',
                                 'KRN-028 selected layout evidence is historical and not rerun.',
                                 'KRN-029 independently archive-qualified XTS source remains valid; its named include-only patch is verified separately.']}
        for name, obj in [('complete-source-manifest.json', corrected), ('historical-requalification.json', assessment)]:
            dump(out / name, obj)
            if a.publish:
                dest = WT / 'fixtures/public/crypto-source-integrity' / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dump(dest, obj)
            else:
                expected = WT / 'fixtures/public/crypto-source-integrity' / name
                must(expected.read_bytes() == (out / name).read_bytes(), 'Published correction differs: ' + name)
        report.update(outcome='pass', summary=assessment['summary'], shared_source_snapshots_preserved=len(snapshots),
                      canonical_sources=corrected['candidates'], patch_controls=patches)
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['finished_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        report['process_memory'] = [s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith(('VmHWM:', 'VmRSS:'))]
        for path in sorted(out.iterdir()):
            if path.is_file() and path.name != 'evidence.json':
                report['artifacts'][str(path.relative_to(WT))] = digest(path.read_bytes())
        dump(out / 'evidence.json', report)
    print(json.dumps({k: report.get(k) for k in ['outcome', 'summary', 'error', 'process_memory']}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
