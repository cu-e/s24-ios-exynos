"""Intentional timeout control: only these owned parent/child processes are stopped."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
child = subprocess.Popen([sys.executable, '-c', 'import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
Path(sys.argv[1]).write_text(json.dumps(dict(parent=os.getpid(), child=child.pid, group=os.getpgrp(), child_group=os.getpgid(child.pid))))
print('READY owned timeout control', flush=True)
time.sleep(60)
