#!/usr/bin/env python3
"""Prepare only STR035's fresh source derivative; no target tool invocation."""
import hashlib
import json
from pathlib import Path
import resource
import shutil
import subprocess
import time

resource.setrlimit(resource.RLIMIT_AS, (256 << 20, 256 << 20))
W = Path(__file__).resolve().parents[3]
M = W.parents[1]
A = W/'artifacts/e1s-kernel-log-objects/source-001'
S = A/'xnu'
H = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
started = time.monotonic()
overlay_path = M/'fixtures/public/e1s-kernel-log/source-overlay.json'
assert H(overlay_path) == '9cda8f05b5a1173a9f49cfdd789c347036f91451ca63abe32a08c82f4be02fda'
o = json.loads(overlay_path.read_bytes())
assert H(o['input_spec']['path']) == o['input_spec']['sha256']
i = json.loads(Path(o['input_spec']['path']).read_bytes())
parent = Path(i['source_root'])
context = json.loads(Path(o['parent_source_context']['path']).read_bytes())
assert H(context['source_manifest']) == o['parent_source_manifest_sha256']
files = json.loads(Path(context['source_manifest']).read_bytes())
assert len(files) == 5111 and set(o['files']) == {'osfmk/arm64/start.s', 'bsd/dev/e1s_log.c'}
assert H(i['git']['path']) == i['git']['sha256']
assert H(o['patch']['path']) == o['patch']['sha256']
A.mkdir(parents=True, exist_ok=False)
S.mkdir()
for name, expected in files.items():
    p = parent/name
    assert p.resolve(strict=True) == p and not p.is_symlink() and H(p) == expected
    target = S/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
commands = []
for argv in [[i['git']['path'], 'init', '--quiet'], [i['git']['path'], 'apply', '--check', o['patch']['path']], [i['git']['path'], 'apply', o['patch']['path']]]:
    r = subprocess.run(argv, cwd=S, text=True, capture_output=True, timeout=10)
    commands.append(dict(argv=argv, cwd=str(S), exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr))
    assert r.returncode == 0
actual = {name:H(S/name) for name in files}
assert {name for name in files if actual[name] != files[name]} == set(o['files'])
assert all(actual[name] == pins['after_sha256'] for name,pins in o['files'].items())
assert all(H(parent/name) == expected for name,expected in files.items())
nodes = [S/'.git', *(S/'.git').rglob('*')]
assert all(not p.is_symlink() for p in nodes)
metadata = dict(root=str(S/'.git'), modes={str(p):p.stat().st_mode & 0o7777 for p in nodes}, files={str(p):H(p) for p in nodes if p.is_file()})
result = dict(schema='e1s-kernel-log-local-source-v1', kind='source-review', origin='local-host', outcome='pass', source_root=str(S), source_files=actual, parent_source_files=files, source_overlay=dict(path=str(overlay_path), sha256=H(overlay_path)), nonsource_metadata=metadata, changed_files=o['files'], source_count=5111, unchanged_files=5109, commands=commands, elapsed_seconds=time.monotonic()-started, self_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024, child_max_rusage_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024, resources_note='256MiB RLIMIT_AS, outer timeout required; rusage is not sampled aggregate RSS.', target_tools_executed=False)
(A/'source-context.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(dict(outcome='pass', source_context=str(A/'source-context.json'), sha256=H(A/'source-context.json'), elapsed_seconds=result['elapsed_seconds'])))
