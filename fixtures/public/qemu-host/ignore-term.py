#!/usr/bin/env python3
"""Owned host-only termination fixture; no guest or device operations."""
import signal
import subprocess
import sys
import time

signal.signal(signal.SIGTERM, signal.SIG_IGN)
subprocess.Popen([sys.executable, "-c",
    "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('independent child process group ready',flush=True);time.sleep(30)"],
    process_group=0)
print("QEMUHOST owned SIGTERM-ignoring host control ready", flush=True)
time.sleep(30)
