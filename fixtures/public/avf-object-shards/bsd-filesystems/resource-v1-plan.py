#!/usr/bin/env python3
"""One original-owner source plan through the accepted shared supervisor/API."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
request = json.loads((HERE / 'resource-v1-request.json').read_text())
helper = Path(request['executor']['path'])
with helper.open('rb') as stream:
    if hashlib.file_digest(stream, 'sha256').hexdigest() != request['executor']['sha256']:
        raise ValueError('Frozen EV executor changed')
spec = importlib.util.spec_from_file_location('vm011_accepted_resource_executor', helper)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
out = Path(request['source_output_parent'])
out.mkdir(parents=True, exist_ok=False)
argv = [sys.executable, '-B', '-s', str(helper), '--mode', 'plan', '--main', request['main'],
        '--task', request['task'], '--owner', request['owner'], '--experiment', request['source_experiment']]
for name in ['manifest', 'qualification', 'selectors']:
    item = request['profile'][name]
    argv.extend(['--' + name, item['path'], '--' + name + '-sha256', item['sha256']])
argv.extend(['--shard', request['shard'], '--resource-profile', 'project-budget-v1', '--out', request['source_output']])
result = policy.run_child(argv, ROOT, out, 'source-plan', policy.supervisor(Path(request['main'])),
                          timeout=120, admit=True)
policy.write(out / 'supervision.json', result)
print(json.dumps({key: result.get(key) for key in ['outcome', 'exit_code', 'elapsed_seconds',
      'peak_total_owned_rss_bytes', 'after']}, indent=2))
sys.exit(0 if result.get('outcome') == 'pass' else 1)
