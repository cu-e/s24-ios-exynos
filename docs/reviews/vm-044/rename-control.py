#!/usr/bin/env python3
"""Actual proc-link ancestry substitution during one live process-table scan."""
import ctypes
from contextlib import ExitStack
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')


def load(path):
    spec = importlib.util.spec_from_file_location('rename_review', path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def one(tool, libc_mode):
    e = load(tool); first = second = None
    stopped=set()
    def stop(process):
        if process.pid in stopped:return
        try:os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:pass
        process.wait(timeout=2)
        stopped.add(process.pid)
    with tempfile.TemporaryDirectory(prefix='real-rename-', dir=HERE) as temporary, ExitStack() as cleanup:
        base = Path(temporary); project = base/'project'; project.mkdir()
        outside = base/'outside'; outside.mkdir()
        childfile = base/'descendant.pid'
        first = subprocess.Popen(['sleep', '20'], cwd=outside, start_new_session=True)
        cleanup.callback(stop, first)
        code = "import pathlib,subprocess,sys,time;p=subprocess.Popen(['sleep','20'],cwd='/tmp');pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(20)"
        second = subprocess.Popen([sys.executable, '-c', code, str(childfile)], cwd=outside, start_new_session=True)
        cleanup.callback(stop, second)
        until = time.monotonic()+2
        while not childfile.exists() and time.monotonic()<until:time.sleep(.005)
        if not childfile.exists():raise RuntimeError('Real descendant did not become observable')
        descendant = int(childfile.read_text()); events = []; moved = project/'moved'
        def seam(path):
            if str(path) not in [f'/proc/{first.pid}/cwd', f'/proc/{second.pid}/cwd']:return
            raw = os.readlink(path)
            events.append({'path':str(path), 'raw_before':raw, 'event':'fresh-live-proc-link'})
            if str(path)==f'/proc/{second.pid}/cwd':
                if raw != str(outside):raise AssertionError('Repeated raw cwd target not established')
                outside.rename(moved); outside.symlink_to(moved, target_is_directory=True)
                events.append({'event':'actual-rename-and-ancestry-symlink', 'raw_after':os.readlink(path)})
        real_cdll = ctypes.CDLL
        real_resolve = Path.resolve
        class Realpath:
            def __init__(self, function):self.function = function
            def __call__(self, path, target):
                seam(os.fsdecode(path)); self.function.argtypes=self.argtypes; self.function.restype=self.restype
                return self.function(path, target)
        class Library:
            def __init__(self, *args, **kwargs):
                self.raw = real_cdll(*args, **kwargs); self.realpath = Realpath(self.raw.realpath); self.free = self.raw.free
        def strict(path, *args, **kwargs):
            seam(path); return real_resolve(path, *args, **kwargs)
        try:
            with patch.object(e.ctypes, 'CDLL', Library) if libc_mode else patch.object(Path, 'resolve', strict):
                table = e.process_table()
            discovered = {pid for pid,row in table.items() if row['cwd'] is not None and Path(row['cwd']).is_relative_to(project)}
            while True:
                expanded = discovered | {pid for pid,row in table.items() if row['ppid'] in discovered}
                if expanded==discovered:break
                discovered=expanded
            report = {'tool':str(tool), 'sha256':e.sha(tool), 'events':events, 'first':table[first.pid], 'second':table[second.pid], 'descendant':table[descendant], 'discovered_second':second.pid in discovered, 'discovered_outside_cwd_descendant':descendant in discovered, 'actual_second_cwd':str(Path(f'/proc/{second.pid}/cwd').resolve(strict=True))}
            report['outcome'] = 'pass' if table[first.pid]['cwd']==str(outside) and table[second.pid]['cwd']==str(moved) and second.pid in discovered and descendant in discovered else 'fail'
            return report
        finally:
            for process in [first, second]:
                stop(process)
            until=time.monotonic()+1
            while True:
                owned_after=[]
                for pid in [first.pid,second.pid,descendant]:
                    try:
                        fields=Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()
                        if fields[0]!='Z' and ('table' not in locals() or int(fields[19])==table[pid]['start_ticks']):owned_after.append({'pid':pid,'state':fields[0]})
                    except (FileNotFoundError,ProcessLookupError):pass
                if not owned_after or time.monotonic()>=until:break
                time.sleep(.005)
            if 'report' in locals():
                report['owned_after']=owned_after
                if owned_after:report['outcome']='fail'


started = time.monotonic(); report={'outcome':'fail', 'argv':[sys.executable, *sys.argv], 'cases':[]}
try:
    old=MAIN/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
    new=MAIN/'worktrees/vm-044-ep-20261106/tools/build/avf_kernel_objects.py'
    report['cases'].append(one(old, False)); report['cases'].append(one(new, True))
    report['outcome']='pass' if all(row['outcome']=='pass' for row in report['cases']) else 'fail'
except Exception as error:report['error']=repr(error)
finally:
    report['elapsed_seconds']=time.monotonic()-started
    (HERE/'rename-control.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}|{'case_outcomes':[row['outcome'] for row in report['cases']]}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
