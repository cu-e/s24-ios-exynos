#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: is the Unicorn model of test_hb_vm.py sensitive to the Darwin ABI facts hb depends on? Host-only.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -W ignore -I docs/procedures/nat-102/abi_mutants.py --out artifacts/nat-102/abi-mutants.json

Each entry breaks ONE fact of the raw system-call layer in src/hb.c (which register carries an argument, the carry convention, the fork child flag, a system call number, a struct
layout, an open flag, a signal number, ...), builds the result with NAT-101's real pipeline (clang + lld + mkstatic) in a scratch tree, runs it under the model in four scenarios
(normal, a hanging ps, a missing ps, failing forks, no console, a child that is gone before wait4) and compares what it did with what the unmutated binary does in the same scenario: exit code, the console text with times and
pids left in, the kills, and any error or fault the model reports. A mutant that behaves exactly like the original in every scenario is reported as UNDETECTED; the exit status is 1 then.

This tests the model, not the phone: a mutant being detected shows that the model would have noticed this particular mistake in hb, not that hb's real ABI assumptions are right.
The facts the model assumes (the fork convention, the carry convention, the select-as-sleep form) are the project XNU's; the native run NAT-103 is their test."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAT101 = ROOT / "docs/procedures/nat-101"

spec = importlib.util.spec_from_file_location("nat102_hb_vm_for_mutants", HERE / "hb_vm.py")
M = importlib.util.module_from_spec(spec)
sys.modules["nat102_hb_vm_for_mutants"] = M
spec.loader.exec_module(M)

# (name, old text in hb.c, new text, the fact it breaks)
MUTANTS = [
    ("fork-child-flag-inverted", "*is_child = (!err && r1 != 0);", "*is_child = (!err && r1 == 0);", "the child is told by x1 != 0"),
    ("fork-child-by-x0", "*is_child = (!err && r1 != 0);", "*is_child = (!err && r0 == 0);", "Darwin returns the parent pid in x0 in the child, not 0"),
    ("carry-ignored", "\treturn err ? -r0 : r0;\n}\n\n/* fork:", "\treturn r0;\n}\n\n/* fork:", "errors come as carry set + errno in x0 (generic call)"),
    ("carry-inverted", "\treturn err ? -r0 : r0;\n}\n\n/* fork:", "\treturn err ? r0 : -r0;\n}\n\n/* fork:", "carry set means failure (generic call)"),
    ("select-timeout-in-x3", "return sc5(SYS_select, 0, 0, 0, 0, (long)&t);", "return sc5(SYS_select, 0, 0, 0, (long)&t, 0);", "select's timeout is the fifth argument (x4)"),
    ("timeval-layout", "\tlong sec;\n\tint usec;\n\tint pad;\n", "\tint usec;\n\tlong sec;\n\tint pad;\n", "struct timeval is {int64 sec, int32 usec}"),
    ("wait4-args-swapped", "sc5(SYS_wait4, pid, (long)status, options, 0, 0)", "sc5(SYS_wait4, pid, options, (long)status, 0, 0)", "wait4(pid, status, options, rusage)"),
    ("wait4-number", "#define SYS_wait4 7", "#define SYS_wait4 11", "wait4 is system call 7"),
    ("execve-args-swapped", "sc5(SYS_execve, (long)path, (long)argv, (long)envp, 0, 0)", "sc5(SYS_execve, (long)path, (long)envp, (long)argv, 0, 0)", "execve(path, argv, envp)"),
    ("dup2-args-swapped", "sc5(SYS_dup2, from, to, 0, 0, 0)", "sc5(SYS_dup2, to, from, 0, 0, 0)", "dup2(old, new)"),
    ("dup2-stderr-missing", "sys_dup2(con, 2);", "(void)con;", "the child's stderr must be the console too"),
    ("dup2-stdout-missing", "sys_dup2(con, 1);", "(void)con;", "the child's stdout must be the console"),
    ("open-readonly", "con = sys_open(CONSOLE_DEV, 2);", "con = sys_open(CONSOLE_DEV, 0);", "the console is opened O_RDWR (2 on Darwin)"),
    ("kill-number", "#define SYS_kill 37", "#define SYS_kill 38", "kill is system call 37"),
    ("kill-signal", "#define SIGKILL 9", "#define SIGKILL 15", "the hung ps is killed with signal 9"),
    ("gettimeofday-tz", "sc5(SYS_gettimeofday, (long)t, 0, 0, 0, 0)", "sc5(SYS_gettimeofday, (long)t, (long)t, 0, 0, 0)", "no tzp and no mach_absolute_time pointer"),
    ("exit127-became-1", "sys_exit(127);", "sys_exit(1);", "a failed exec exits 127 (wait status 32512)"),
    ("fork-number", "#define SYS_fork 2", "#define SYS_fork 3", "fork is system call 2"),
    ("write-number", "#define SYS_write 4", "#define SYS_write 3", "write is system call 4"),
    ("poll-wait-not-nohang", "#define WNOHANG 1", "#define WNOHANG 0", "WNOHANG is 1 on Darwin"),
    ("fork-carry-ignored", "\t*is_child = (!err && r1 != 0);\n\treturn err ? -r0 : r0;", "\t*is_child = (!err && r1 != 0);\n\treturn r0;", "a failed fork returns errno in x0 with the carry set (fork call)"),
    ("fork-child-ignores-carry", "*is_child = (!err && r1 != 0);", "*is_child = (r1 != 0);", "x1 is meaningful only when the carry is clear"),
]

SCENARIOS = {
    "normal": dict(),
    "hang": dict(plan=lambda n, argv: dict(mode="hang") if n == 2 else dict(mode="ok", us=120000)),
    "missing-ps": dict(ps_path=b"/bin/nonexistent"),
    "fork-fails": dict(fork_fail_rounds=(1, 2)),
    "no-console": dict(console_ok=False),               # open() fails: the only place where hb acts on an errno of the generic call
    "child-gone": dict(reaped_elsewhere=True),          # wait4() fails with ECHILD
}

# A mutant that no scenario can tell from the original is either a gap in the model or equivalent in the real kernel; only the second is allowed, with the source that shows it.
EQUIVALENT = {
    "fork-child-ignores-carry": "references/apple-xnu/bsd/dev/arm/systemcalls.c, arm_prepare_u64_syscall_return(): on an error the kernel stores x[0] = error and x[1] = 0 and sets the carry, so "
                                "x1 != 0 can only be read after a success and the extra !err test changes nothing; the model leaves x1 at 0 on an error likewise",
}


def behave(macho, kw):
    k = M.Kernel(schedule="wait", **kw)
    try:
        M.VM(macho, k).run(chunk=2_000_000)
    except M.Failure as e:
        return ("failure", str(e)[:200], k.console_text()[:400])
    return ("ok", k.exit_code, k.console_text(), tuple(k.kills), tuple(k.errors))


def build_in_scratch(text, tmp):
    scratch = Path(tmp)
    proc = scratch / "docs/procedures"
    proc.mkdir(parents=True)
    shutil.copytree(NAT101, proc / "nat-101", ignore=shutil.ignore_patterns("__pycache__"))
    for p in (ROOT / "docs/procedures").iterdir():
        if p.name != "nat-101":
            os.symlink(p, proc / p.name)
    for top in ("artifacts", "tools", "references"):
        os.symlink(ROOT / top, scratch / top)
    (proc / "nat-101/src/hb.c").write_text(text)
    out = scratch / "out"
    r = subprocess.run([sys.executable, "-B", "-I", str(proc / "nat-101/build_hb.py"), "--out", str(out)], capture_output=True, text=True, cwd=str(scratch), timeout=180)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip().splitlines()[-1:]
    return (out / "hb").read_bytes(), None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit("--out exists: %s" % a.out)
    src = (NAT101 / "src/hb.c").read_text()
    with tempfile.TemporaryDirectory(prefix="nat102-abi-", dir=os.environ.get("TMPDIR")) as tmp:
        base_macho, err = build_in_scratch(src, tmp + "/base")
        if base_macho is None:
            raise SystemExit("the unmutated source does not build: %s" % (err,))
        base = {n: behave(base_macho, kw) for n, kw in SCENARIOS.items()}
        for n, b in base.items():
            if b[0] != "ok" or b[1] not in (0, 2):
                raise SystemExit("the unmutated binary does not behave under scenario %s: %r" % (n, b[:2]))
        report, undetected = [], []
        for i, (name, old, new, fact) in enumerate(MUTANTS):
            if src.count(old) != 1:
                raise SystemExit("mutant %s: expected exactly one occurrence of %r, found %d" % (name, old, src.count(old)))
            macho, err = build_in_scratch(src.replace(old, new), "%s/m%02d" % (tmp, i))
            if macho is None:
                report.append(dict(name=name, fact=fact, result="invalid (does not build)", detail=err))
                continue
            seen = [n for n, kw in SCENARIOS.items() if behave(macho, kw) != base[n]]
            if seen:
                report.append(dict(name=name, fact=fact, result="detected", scenarios=seen))
            elif name in EQUIVALENT:
                report.append(dict(name=name, fact=fact, result="equivalent", reason=EQUIVALENT[name], scenarios=[]))
            else:
                report.append(dict(name=name, fact=fact, result="UNDETECTED", scenarios=[]))
                undetected.append(name)
    a.out.write_text(json.dumps(dict(source_sha256=__import__("hashlib").sha256(src.encode()).hexdigest(), mutants=report, undetected=undetected), indent=1))
    for r in report:
        print("%-26s %s %s" % (r["name"], r["result"], ",".join(r.get("scenarios", []))))
    return 1 if undetected else 0


if __name__ == "__main__":
    sys.exit(main())
