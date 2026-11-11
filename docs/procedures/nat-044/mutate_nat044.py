#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Mutation check for NAT-044: break one line of the new code at a time in a scratch copy of the procedure trees and require
test_nat044.py to fail. Host-only; it writes under --out and under the system temp directory and nowhere else.

    capvenv/bin/python -I docs/procedures/nat-044/mutate_nat044.py --out artifacts/nat-044/mutation-001 [--jobs 4]

Run it with an interpreter that has unicorn and capstone: several mutants (for instance the removal of the deadline poll from the
busy wait) are visible only to the aarch64 layers. A mutant that no longer builds (`build.py --check-only` fails) is INVALID, not
killed, and counts against the run. A mutant that is not killed makes the exit status non-zero."""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

# (name, file relative to nat-044, old, new); `old` must occur exactly once in the file
MUTANTS = [
    # --- the glue
    ("the-reset-is-attempted-repeatedly", "src/markerlib4.c", "\tg_nat044.armed = 0;\n\tg_nat044.fired = 1;", "\tg_nat044.fired = 1;"),
    ("deadline-compare-inverted", "src/markerlib4.c", "if (mk_cnt() - g_nat044.t0 < g_nat044.deadline_ticks)", "if (mk_cnt() - g_nat044.t0 > g_nat044.deadline_ticks)"),
    ("reset-marker-never-drawn", "src/markerlib4.c", "\tmk_draw(mk_frame(MK_STAGE, 0, MK_ST_RESET), 0, 1);\n", ""),
    ("reset-marker-drawn-after-the-trigger", "src/markerlib4.c",
     "\tmk_draw(mk_frame(MK_STAGE, 0, MK_ST_RESET), 0, 1);\n\tg_nat044.rc = (uint32_t)(-s5e_reset_to(g_nat044.pmu, NAT044_REASON)) & NAT044_ST_RC_MASK;\n",
     "\tg_nat044.rc = (uint32_t)(-s5e_reset_to(g_nat044.pmu, NAT044_REASON)) & NAT044_ST_RC_MASK;\n\tmk_draw(mk_frame(MK_STAGE, 0, MK_ST_RESET), 0, 1);\n"),
    ("rc-not-negated", "src/markerlib4.c", "(uint32_t)(-s5e_reset_to(g_nat044.pmu, NAT044_REASON))", "(uint32_t)(s5e_reset_to(g_nat044.pmu, NAT044_REASON))"),
    ("reason-hard-coded-normal", "src/markerlib4.c", "s5e_reset_to(g_nat044.pmu, NAT044_REASON)", "s5e_reset_to(g_nat044.pmu, S5E_REASON_NORMAL)"),
    ("reset-to-wrong-pmu", "src/markerlib4.c", "s5e_reset_to(g_nat044.pmu, NAT044_REASON)", "s5e_reset_to(g_nat044.pmu + 1, NAT044_REASON)"),
    ("result-frame-not-drawn", "src/markerlib4.c", "\tmk_draw(mk_frame(MK_RST, 7, nat044_status()), 0, 1);\t/* only reached when nothing was triggered */\n", ""),
    ("snapshot-does-not-clear-download", "src/markerlib4.c", "if (s.inform3 == S5E_REASON_DOWNLOAD || s.inform3 == S5E_REASON_BOOTLOADER)", "if (s.inform3 == S5E_REASON_BOOTLOADER)"),
    ("snapshot-does-not-clear-bootloader", "src/markerlib4.c", "if (s.inform3 == S5E_REASON_DOWNLOAD || s.inform3 == S5E_REASON_BOOTLOADER)", "if (s.inform3 == S5E_REASON_DOWNLOAD)"),
    ("snapshot-clears-every-word", "src/markerlib4.c", "if (s.inform3 == S5E_REASON_DOWNLOAD || s.inform3 == S5E_REASON_BOOTLOADER)", "if (s.inform3 != S5E_REASON_NORMAL)"),
    ("snapshot-clear-result-swapped", "src/markerlib4.c", "== S5E_REASON_NORMAL ? 1u : 2u;", "== S5E_REASON_NORMAL ? 2u : 1u;"),
    ("snapshot-clear-not-read-back", "src/markerlib4.c", "g_nat044.cleared = pmu[S5E_PMU_INFORM3 / 4u] == S5E_REASON_NORMAL ? 1u : 2u;", "g_nat044.cleared = 1u;"),
    ("snapshot-entry-words-swapped", "src/markerlib4.c", "\tg_nat044.inform2_0 = s.inform2;\n\tg_nat044.inform3_0 = s.inform3;\n", "\tg_nat044.inform2_0 = s.inform3;\n\tg_nat044.inform3_0 = s.inform2;\n"),
    ("snapshot-pmu-not-remembered", "src/markerlib4.c", "\tg_nat044.pmu = pmu;\n", ""),
    ("arm-without-a-known-pmu", "src/markerlib4.c", "g_nat044.armed = g_nat044.pmu != 0;", "g_nat044.armed = 1;"),
    ("start-time-not-taken", "src/markerlib4.c", "\tg_nat044.t0 = mk_cnt();\n", ""),
    ("deadline-ticks-divided", "src/markerlib4.c", "mk_freq() * (uint64_t)NAT044_DEADLINE_S", "mk_freq() / (uint64_t)NAT044_DEADLINE_S"),
    ("zero-deadline-still-arms", "src/markerlib4.c", "#if NAT044_DEADLINE_S > 0\n", "#if 1\n"),
    ("status-armed-bit-dropped", "src/markerlib4.c", "(n->armed ? NAT044_ST_ARMED : 0) |", "0 |"),
    ("status-fired-bit-dropped", "src/markerlib4.c", "(n->fired ? NAT044_ST_FIRED : 0) |", "0 |"),
    ("status-cleared-bit-dropped", "src/markerlib4.c", "(n->cleared == 1 ? NAT044_ST_CLEARED : 0) |", "0 |"),
    ("status-clear-failed-bit-dropped", "src/markerlib4.c", "(n->cleared == 2 ? NAT044_ST_CLEARFAIL : 0)", "0"),
    ("report-inform3-halves-swapped", "src/markerlib4.c", "show(prev, mk_frame(MK_RST, 0, n->inform3_0 >> 16), k);", "show(prev, mk_frame(MK_RST, 0, n->inform3_0 & 0xffffu), k);"),
    ("report-reboot-cmd-frame-missing", "src/markerlib4.c", "\tshow(prev, mk_frame(MK_RST, 5, n->cmd_0 & 0xffffu), k);\n", ""),
    ("report-shows-inform2-as-inform3", "src/markerlib4.c", "show(prev, mk_frame(MK_RST, 2, n->inform2_0 >> 16), k);", "show(prev, mk_frame(MK_RST, 2, n->inform3_0 >> 16), k);"),
    # --- the header
    ("status-fired-bit-moved", "src/reset44.h", "#define NAT044_ST_FIRED      0x1000u", "#define NAT044_ST_FIRED      0x0800u"),
    ("status-armed-bit-moved", "src/reset44.h", "#define NAT044_ST_ARMED      0x2000u", "#define NAT044_ST_ARMED      0x2001u"),
    ("barrier-dropped-on-the-target", "src/reset44.h", '#define NAT044_BARRIER() __asm__ volatile("dsb sy" ::: "memory")', '#define NAT044_BARRIER() __asm__ volatile("" ::: "memory")'),
    # --- the source patch
    ("patch-deadline-not-polled-in-the-busy-wait", "patch_loader4.py", "while (mk_cnt() - s < t) { nat044_tick(); }", "while (mk_cnt() - s < t) { }"),
    ("patch-deadline-not-polled-when-waits-are-skipped", "patch_loader4.py", "\\t(void)tenths;\\n\\tnat044_tick();\\n#endif", "\\t(void)tenths;\\n#endif"),
    ("patch-report-not-shown-in-the-hold-loop", "patch_loader4.py", "\\t\\tnat044_show(&prev, &ld_k);\\n", "\\t\\t/* nat044_show removed */\\n"),
    ("patch-snapshot-call-missing", "patch_loader4.py", '"    nat044_snapshot(pmu);\\n    diagnostic_value(\\"panic_inform_before\\",pmu[0xbc/4]);\\n"', '"    diagnostic_value(\\"panic_inform_before\\",pmu[0xbc/4]);\\n"'),
    ("patch-arm-before-the-watchdog", "patch_loader4.py", '"    if (s5e_wdt_arm(&w,83)) return -1;\\n    nat044_arm();\\n"', '"    nat044_arm();\\n    if (s5e_wdt_arm(&w,83)) return -1;\\n"'),
    ("patch-arm-call-missing", "patch_loader4.py", '"    if (s5e_wdt_arm(&w,83)) return -1;\\n    nat044_arm();\\n"', '"    if (s5e_wdt_arm(&w,83)) return -1;\\n"'),
    ("patch-frame-kind-collides", "patch_loader4.py", "MK_RST = 14\\t/*", "MK_RST = 13\\t/*"),
    ("patch-reset-stage-code-changed", "patch_loader4.py", "MK_ST_RESET = 0x41\\t/*", "MK_ST_RESET = 0x42\\t/*"),
    ("patch-wdt-seconds-overstated", "patch_loader4.py", "return int(m.group(1))", "return int(m.group(1)) + 100"),
    # --- the build
    ("build-margin-removed", "build.py", "MIN_MARGIN_S = 20 ", "MIN_MARGIN_S = 0 "),
    ("build-accepts-a-zero-deadline", "build.py", "if not 0 < deadline_s <= wdt - MIN_MARGIN_S:", "if not 0 <= deadline_s <= wdt - MIN_MARGIN_S:"),
    ("build-images-get-each-other-s-reason", "build.py", 'f"-DNAT044_REASON={reason_name}"', 'f"-DNAT044_REASON={REASONS[[k for k in REASONS if k != name][0]][0]}"'),
    ("build-record-states-the-wrong-reason", "build.py", 'meta[name] = {"reason": f"{reason:#010x}",', 'meta[name] = {"reason": f"{reason + 1:#010x}",'),
    ("build-deadline-not-passed-to-the-glue", "build.py", 'f"-DNAT044_DEADLINE_S={deadline_s}", ', 'f"-DNAT044_DEADLINE_S=44", '),
    # --- the package
    ("package-takes-the-loader-image-alone", "package.py", 'payload = a.build / meta["path"]', 'payload = a.build / build["images"][name]["path"]'),
    ("package-records-the-wrong-offset", "package.py", "payload_offset=off,", "payload_offset=off + 4,"),
    ("package-records-the-wrong-size", "package.py", "payload_bytes=len(data),", "payload_bytes=len(data) - 1,"),
    # --- the decoder
    ("decoder-inform3-halves-swapped", "decode44.py", "R_INFORM3 = (0, 1)", "R_INFORM3 = (1, 0)"),
    ("decoder-status-armed-bit-wrong", "decode44.py", "ST_RC_MASK, ST_FIRED, ST_ARMED, ST_CLEARED, ST_CLEARFAIL = 0x00FF, 0x1000, 0x2000, 0x4000, 0x8000",
     "ST_RC_MASK, ST_FIRED, ST_ARMED, ST_CLEARED, ST_CLEARFAIL = 0x00FF, 0x1000, 0x4000, 0x2000, 0x8000"),
    ("decoder-result-frame-index-wrong", "decode44.py", "R_RESULT = 7 ", "R_RESULT = 6 "),
]


def make_tree(dst, mutated=None):
    """docs/procedures/{nat-022,nat-042,nat-044} copied, artifacts linked to the real ones (read-only inputs)."""
    base = Path(dst) / "docs" / "procedures"
    base.mkdir(parents=True)
    for n in ("nat-022", "nat-042", "nat-044"):
        shutil.copytree(ROOT / "docs/procedures" / n, base / n, ignore=shutil.ignore_patterns("__pycache__", "evidence.json", "summary.json", "mutation*"))
    os.symlink(ROOT / "artifacts", Path(dst) / "artifacts")
    for extra in ("tools", "devices"):                       # read-only inputs of the NAT-022 packager (NAT-006 builder, pinned stock RECOVERY)
        if (ROOT / extra).exists():
            os.symlink(ROOT / extra, Path(dst) / extra)
    if mutated:
        f = base / "nat-044" / mutated[0]
        f.write_text(f.read_text().replace(mutated[1], mutated[2]))
    return Path(dst)


def builds(tree):
    r = subprocess.run([sys.executable, "-I", str(tree / "docs/procedures/nat-044/build.py"), "--check-only", "--loader-source",
                        str(ROOT / "artifacts/nat-020/build-003/source")], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout)[-300:]


def run_tests(tree, timeout):
    try:
        r = subprocess.run([sys.executable, "-I", str(tree / "docs/procedures/nat-044/test_nat044.py")], capture_output=True, text=True,
                           timeout=timeout, cwd=tree)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return r.returncode, r.stderr[-500:]


def one(i, mutant, tmp, timeout):
    name, rel, old, new = mutant
    src = (HERE / rel).read_text()
    n = src.count(old)
    if n != 1:
        return dict(name=name, status="ANCHOR", detail="anchor occurs %d times in %s" % (n, rel))
    tree = make_tree(Path(tmp) / ("m%02d" % i), (rel, old, new))
    try:
        # the mutants of the decoder and of the test-facing pieces do not need to build; every other one must
        if rel != "decode44.py":
            ok, why = builds(tree)
            if not ok and name not in ("build-margin-removed", "build-accepts-a-zero-deadline"):
                return dict(name=name, status="INVALID", detail=why)
        rc, tail = run_tests(tree, timeout)
        return dict(name=name, status="killed" if rc != 0 else "SURVIVED", exit=rc, detail="" if rc != 0 else "tests passed")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="nat044-mut-") as tmp:
        base = make_tree(Path(tmp) / "base")
        rc, tail = run_tests(base, a.timeout)
        if rc != 0:
            print("baseline fails; refusing to judge mutants:\n" + str(tail))
            return 2
        results = []
        with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
            futs = [ex.submit(one, i, m, tmp, a.timeout) for i, m in enumerate(MUTANTS)]
            for f in futs:
                r = f.result()
                results.append(r)
                print("%-58s %s %s" % (r["name"], r["status"], r.get("detail", "")[:120]), flush=True)
    killed = sum(1 for r in results if r["status"] == "killed")
    summary = dict(total=len(MUTANTS), killed=killed, not_killed=len(MUTANTS) - killed, invalid=sum(1 for r in results if r["status"] == "INVALID"),
                   interpreter_has_unicorn_and_capstone=_has_sim(), results=results)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("killed %d of %d" % (killed, len(MUTANTS)))
    return 0 if killed == len(MUTANTS) else 1


def _has_sim():
    try:
        import unicorn, capstone  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
