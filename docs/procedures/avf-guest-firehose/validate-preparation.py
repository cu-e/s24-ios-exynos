"""Read-only checks for the final source-preparation artifact boundary."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[3]
run = Path(__file__).parent / 'preparation-session3'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

ast.parse((root / 'tools/build/avf_guest_firehose.py').read_text())
evidence = json.loads((run / 'evidence.json').read_text())
plan = json.loads((run / 'compile-plan.json').read_text())
assert evidence['outcome'] == 'pass' and evidence['compiled'] is False
assert len(evidence['controls']) == 4 and all(r['rejected'] for r in evidence['controls'])
assert len(plan['recipes']) == 3
assert not list(run.rglob('*.o')) and not list(run.rglob('*.a'))
assert sha(root / 'tools/build/avf_guest_firehose.py') == evidence['builder']['sha256']
for row in plan['recipes']:
    assert '-DARM64_BOARD_CONFIG_BCM2837' in row['argv_template']
    assert not any('ARM64_BOARD_CONFIG_E1S' in a for a in row['argv_template'])
    assert row['source']['sha256'] == sha(row['source']['path'])
for item in evidence['probe_inputs']:
    assert item['snapshot']['sha256'] == sha(item['snapshot']['path'])
    assert Path(item['snapshot']['path']).is_relative_to(run)
for command in evidence['commands']:
    assert Path(command['argv'][0]).name in ('git', 'unifdef')
result = subprocess.run(['git', 'diff', '--check'], cwd=root, capture_output=True)
assert result.returncode == 0, result.stderr.decode()
print(json.dumps(dict(kind='host-test', outcome='pass', task='VM-020',
    recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    command=['python3', '-s', str(Path(__file__).resolve())], exit_code=0,
    validator_sha256=sha(__file__), evidence_sha256=sha(run / 'evidence.json'),
    plan_sha256=sha(run / 'compile-plan.json'),
    checks=['AST syntax', 'four recipe mutation rejections', 'three guest recipes',
            'current builder and immutable probe snapshot hashes', 'Git/unifdef-only child commands',
            'no objects or archives', 'git diff --check exit 0'],
    source_preparation_only=True, task_acceptance_complete=False), indent=2))
