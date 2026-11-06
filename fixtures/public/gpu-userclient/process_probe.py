#!/usr/bin/env python3
"""Python-only cancellation fixture. Never compiler, sanitizer or GPU work."""
import json
import os
from pathlib import Path
import signal
import sys
import time

out=Path(sys.argv[1])
if sys.argv[2]=="exit": sys.exit(0)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=os.fork()
if child==0:
    os.setpgrp()
    (out/"group-ready").write_text(str(os.getpid()))
    time.sleep(30)
    os._exit(0)
until=time.monotonic()+2
while not (out/"group-ready").exists():
    if time.monotonic()>until: raise RuntimeError("Fixture group did not start")
    time.sleep(.01)
def identity(pid):
    fields=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
    return {"pid":pid,"start_ticks":int(fields[19]),"pgrp":int(fields[2]),"session":int(fields[3])}
(out/"probe-ready.tmp").write_text(json.dumps([identity(os.getpid()),identity(child)]))
(out/"probe-ready.tmp").replace(out/"probe-ready.json")
time.sleep(30)
