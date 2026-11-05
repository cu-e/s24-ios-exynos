#!/usr/bin/env python3
"""One tiny genuine selected-header compile; no candidate/algorithm build."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WT = HERE.parents[2]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
sys.dont_write_bytecode = True
sys.path.insert(0, str(WT / 'tools/build'))
from xnu_kernel_syscalls import ObjectData


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    a = p.parse_args()
    out = HERE / 'local' / a.run
    if out.resolve() != out or '/' in a.run or not a.run:
        raise ValueError('Fresh canonical run required')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(kind='source-review', origin='local-host', outcome='fail',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  summary='Attempted one genuine selected-header layout compile', commands=[])
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0'}
    try:
        parent = MAIN / 'artifacts/xnu-kernel-declarations/controls-session1/report.json'
        original = json.loads(parent.read_text())
        source = MAIN / original['source_ports']['osfmk/mc_provider.o']['source']
        command = next(row for row in original['commands'] if str(source) in row['argv'] and '-c' in row['argv'])
        argv = list(command['argv'])
        if sha(Path(argv[0])) != original['compiler_sha256']:
            raise ValueError('Actual compiler changed')
        expressions = {
            'ccmode_ecb_bytes': 'sizeof(struct ccmode_ecb)',
            'ccmode_cbc_bytes': 'sizeof(struct ccmode_cbc)',
            'ccmode_xts_bytes': 'sizeof(struct ccmode_xts)',
            'ccmode_gcm_bytes': 'sizeof(struct ccmode_gcm)',
            'ecb_context_alignment': '_Alignof(ccecb_ctx)',
            'cbc_context_alignment': '_Alignof(cccbc_ctx)',
            'xts_context_alignment': '_Alignof(ccxts_ctx)',
            'gcm_context_alignment': '_Alignof(ccgcm_ctx)',
            'chacha_context_bytes': 'sizeof(ccchacha20poly1305_ctx)',
            'chacha_context_alignment': '_Alignof(ccchacha20poly1305_ctx)',
            'fixed_xts_encrypt_context_bytes': 'sizeof(((symmetric_xts *)0)->enc)',
            'fixed_xts_decrypt_context_bytes': 'sizeof(((symmetric_xts *)0)->dec)',
            'fixed_aes_cbc_context_bytes': 'sizeof(aes_encrypt_ctx)',
            'fixed_rsa_public_context_bytes': 'sizeof(rsa_pub_ctx)',
            'rsa_public_context_alignment': '_Alignof(rsa_pub_ctx)',
            'rsa_max_key_bits': 'RSA_MAX_KEY_BITSIZE',
        }
        probe, obj, dep = out / 'layout.c', out / 'layout.o', out / 'layout.d'
        probe.write_text('#include <libkern/crypto/register_crypto.h>\n#include <libkern/crypto/aesxts.h>\n#include <libkern/crypto/aes.h>\n#include <libkern/crypto/rsa.h>\n__attribute__((used)) const unsigned long long candidate_requirements_layout[] = {' + ','.join(expressions.values()) + '};\n')
        argv[argv.index(str(source))] = str(probe)
        argv[argv.index('-o') + 1] = str(obj)
        argv[argv.index('-MF') + 1] = str(dep)
        result = subprocess.run(argv, cwd=command['cwd'], env=env, capture_output=True, timeout=45)
        stdout, stderr = out / 'compile.stdout.txt', out / 'compile.stderr.txt'
        stdout.write_bytes(result.stdout)
        stderr.write_bytes(result.stderr)
        report['commands'].append(dict(argv=argv, cwd=command['cwd'], exit_code=result.returncode,
                                       stdout=str(stdout.relative_to(MAIN)), stderr=str(stderr.relative_to(MAIN))))
        if result.returncode:
            raise ValueError('Genuine target layout compile failed')
        values = ObjectData(obj).value('_candidate_requirements_layout', '<16Q')
        report['target_layout'] = dict(zip(expressions, values))
        report['compiler'] = dict(path=argv[0], sha256=sha(Path(argv[0])), target='arm64-apple-ios16.5')
        report['parent'] = dict(path=str(parent.relative_to(MAIN)), sha256=sha(parent))
        dependencies = dep.read_text().replace('\\\n', ' ').splitlines()[0].split(':', 1)[1].split()
        report['dependency_hashes'] = {}
        for name in dependencies:
            path = Path(name) if Path(name).is_absolute() else Path(command['cwd']) / name
            report['dependency_hashes'][str(path.resolve())] = sha(path)
        peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
        if peak > 256 * 1024:
            raise ValueError('Child exceeded256MiB RSS')
        report['peak_child_RSS_KiB'] = peak
        report['outcome'] = 'pass'
        report['summary'] = 'One real selected-header target object measures descriptor/alignment/fixed caller storage; no backend algorithm or registration executed'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        (out / 'measure_layout.py').write_bytes(Path(__file__).read_bytes())
        paths = [p for p in sorted(out.rglob('*')) if p.is_file()]
        report['artifacts'] = [str(p.relative_to(MAIN)) for p in paths]
        report['sha256'] = {str(p.relative_to(MAIN)): sha(p) for p in paths}
        (out / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'target_layout', 'peak_child_RSS_KiB']}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
