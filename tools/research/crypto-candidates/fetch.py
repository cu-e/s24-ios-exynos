#!/usr/bin/env python3
"""Explicit pinned public-source acquisition into owned ignored storage only."""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import resource
import re
import subprocess
import urllib.request
import zipfile

HERE = Path(__file__).resolve().parent
FIX = HERE.parents[2] / 'fixtures/public/crypto-candidates'


def target(base, name):
    if not base.resolve().is_relative_to(HERE):
        raise ValueError('Source directory escapes owned tool storage')
    if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
        raise ValueError('Invalid named source path')
    p = base / name
    if not p.resolve().is_relative_to(base.resolve()):
        raise ValueError('Source symlink escapes owned storage')
    return p


def checked_write(p, data, expected):
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Pinned source bytes differ: ' + str(p))
    if p.exists() and p.read_bytes() != data:
        raise ValueError('Do not overwrite changed source; preserve and use a fresh cache')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache-root', type=Path, default=HERE / 'local')
    a = p.parse_args()
    base = a.cache_root.resolve()
    if not base.is_relative_to(HERE) or base == HERE:
        raise ValueError('Cache must remain under owned tool directory')
    base.mkdir(parents=True, exist_ok=True)
    if (base / 'fetch-evidence.json').exists():
        raise ValueError('Keep acquisition evidence immutable; use a fresh cache root')
    corpus = json.loads((FIX / 'candidates.json').read_text())
    vectors = json.loads((FIX / 'vector-inputs.json').read_text())
    report = dict(kind='source-review', origin='local-host', outcome='fail',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  summary='Attempted explicit pinned named public-source acquisition', commands=[], downloads=[])
    env = {**os.environ, 'GIT_NO_LAZY_FETCH': '1', 'GIT_OPTIONAL_LOCKS': '0'}

    def run(args, expected=0):
        r = subprocess.run(list(map(str, args)), env=env, capture_output=True, timeout=45)
        report['commands'].append(dict(argv=list(map(str, args)), exit_code=r.returncode,
                                       stderr=r.stderr.decode(errors='replace')[-1800:]))
        if r.returncode != expected:
            raise ValueError('Actual Git acquisition command failed')
        if resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss > 256 * 1024:
            raise ValueError('Git child exceeded256MiB RSS')
        return r.stdout

    def download(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 's24-pinned-source-audit'}), timeout=30) as r:
            data = r.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError('Named source acquisition exceeds2MiB bound')
            report['downloads'].append(dict(url=url, http_status=r.status, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
            return data
    try:
        for candidate, facts in corpus['candidates'].items():
            if candidate not in ['mbedtls', 'bearssl'] or not re.fullmatch('[0-9a-f]{40}', facts['revision']):
                raise ValueError('Only reviewed public candidate pins are allowed')
            if candidate == 'bearssl':
                repo = base / 'bearssl.git'
                if repo.is_symlink() or not repo.resolve().is_relative_to(base):
                    raise ValueError('Owned Git storage must not alias a shared repository')
                if not repo.exists():
                    run(['git', 'init', '--bare', repo])
                    run(['git', '-C', repo, '-c', 'pack.threads=1', '-c', 'pack.windowMemory=32m', 'fetch',
                         '--depth=1', '--no-tags', 'https://www.bearssl.org/git/BearSSL', facts['revision']])
            for name, evidence in facts['files'].items():
                path = target(base / candidate, name)
                if path.is_file():
                    data = path.read_bytes()
                elif candidate == 'mbedtls':
                    data = download('https://raw.githubusercontent.com/Mbed-TLS/mbedtls/' + facts['revision'] + '/' + name)
                else:
                    data = run(['git', '-C', repo, 'show', facts['revision'] + ':' + name])
                checked_write(path, data, evidence['sha256'])
        for archive in vectors['archives']:
            path = target(base / 'vectors', archive['archive'])
            data = path.read_bytes() if path.is_file() else download(archive['url'])
            checked_write(path, data, archive['archive_sha256'])
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for member in archive['members']:
                    checked_write(target(base / 'vectors', member['member']), z.read(member['member']), member['sha256'])
        report['outcome'] = 'pass'
        report['summary'] = 'Pinned named source/license/vector bytes acquired or verified in isolated cache; nothing built or executed'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        (base / 'fetch-evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'error', 'summary']}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
