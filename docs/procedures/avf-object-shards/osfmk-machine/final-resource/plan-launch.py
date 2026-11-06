"""Finite source-plan supervision only; shared EV helper owns all validation."""
import hashlib
import json
import os
from pathlib import Path
import resource
import runpy
import signal
import sys
import time

request = json.loads(Path(sys.argv[1]).read_text())
argv = request['plan_argv']
assert argv[argv.index('--mode')+1] == 'plan'
assert argv[argv.index('--resource-profile')+1] == 'project-budget-v1'
assert request['source_only'] is True and request['compiler_authorized'] is False
assert not Path(request['actual_output']).exists()
with Path(argv[0]).open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == request['helper_sha256']
resource.setrlimit(resource.RLIMIT_AS, (268435456, 268435456))
def deadline(signum, frame):
    raise KeyboardInterrupt('Root source-plan120s deadline')
signal.signal(signal.SIGALRM, deadline)
signal.signal(signal.SIGTERM, deadline)
signal.setitimer(signal.ITIMER_REAL, 120)
started, samples, exit_code = time.monotonic(), [], 1
try:
    for number in range(3):
        available = next(int(line.split()[1])*1024 for line in
            Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        samples.append(available)
        assert available >= 4*1024**3, 'Stable4GiB floor not available'
        if number < 2:
            time.sleep(1)
    sys.argv = argv
    sys.path.insert(0, str(Path(argv[0]).parent))
    runpy.run_path(argv[0], run_name='__main__')
    exit_code = 0
except SystemExit as exc:
    exit_code = exc.code if type(exc.code) is int else 1
    raise
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
    completion = Path(request['completion'])
    completion.parent.mkdir(parents=True, exist_ok=True)
    completion.write_text(json.dumps({'source_only':True, 'pid':os.getpid(),
        'exit_code':exit_code, 'elapsed_seconds':time.monotonic()-started,
        'mem_available_samples':samples, 'address_space_limit_bytes':268435456,
        'whole_timeout_seconds':120, 'actual_output_absent':not Path(request['actual_output']).exists(),
        'children_after':Path('/proc/self/task/'+str(os.getpid())+'/children').read_text().strip(),
        'vmhwm_bytes':next(int(line.split()[1])*1024 for line in
            Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:'))},indent=2)+'\n')
