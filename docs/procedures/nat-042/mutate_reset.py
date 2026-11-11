#!/usr/bin/env python3
"""Mutation check for the NAT-042 reset module: change one line of module/s5e9945_reset.{c,h} at a time in a scratch
copy and require test/host_test.c to fail. A mutant that does not compile is reported as INVALID (not counted as
killed); a mutant that passes is SURVIVED. Host-only; writes only under --out and a temporary directory.

    python3 -I docs/procedures/nat-042/mutate_reset.py --out artifacts/nat-042/mutation
"""
import argparse, json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
C, H = "s5e9945_reset.c", "s5e9945_reset.h"
# (name, file, old, new): `old` must occur exactly once
MUTANTS = [
    ("inform2-not-read-modify-write", C, "(S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM2)) & ~(S5E_INFORM2_BYTE_MASK << S5E_INFORM2_BYTE_SHIFT))", "0"),
    ("inform2-byte-mask-too-narrow", C, "~(S5E_INFORM2_BYTE_MASK << S5E_INFORM2_BYTE_SHIFT))", "~(0xfu << S5E_INFORM2_BYTE_SHIFT))"),
    ("inform2-byte-in-wrong-position", C, "| (S5E_INFORM2_NORMAL << S5E_INFORM2_BYTE_SHIFT);", "| (S5E_INFORM2_NORMAL << 24);"),
    ("inform2-verify-removed", C, "    if (S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM2)) != w2) return S5E_RESET_EVERIFY2;\n", ""),
    ("inform3-gets-an-extra-bit", C, "S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM3), reason);", "S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM3), reason | 0x10u);"),
    ("inform3-verify-removed", C, "    if (S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM3)) != reason) return S5E_RESET_EVERIFY3;\n", ""),
    ("inform3-barrier-removed", C, "S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM3), reason);\n    S5E_BARRIER();\n", "S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM3), reason);\n"),
    ("cmd-mode-mask-too-narrow", H, "#define S5E_MODE_MASK           0x7u", "#define S5E_MODE_MASK           0x3u"),
    ("cmd-verify-compares-every-bit", C, "if (((S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) ^ wc) & S5E_MODE_MASK) != 0) return S5E_RESET_EVERIFYC;", "if (S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) != wc) return S5E_RESET_EVERIFYC;"),
    ("cmd-verify-removed", C, "    if (((S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) ^ wc) & S5E_MODE_MASK) != 0) return S5E_RESET_EVERIFYC;\n", ""),
    ("cmd-verify-ignores-mode-bits", C, "if (((S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) ^ wc) & S5E_MODE_MASK) != 0)", "if (((S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) ^ wc) & 0x100u) != 0)"),
    ("recovery-reason-accepted", C, "&& reason != S5E_REASON_BOOTLOADER)", "&& reason != S5E_REASON_BOOTLOADER && reason != 0x12345604u)"),
    ("reason-check-removed", C, "    if (reason != S5E_REASON_NORMAL && reason != S5E_REASON_DOWNLOAD && reason != S5E_REASON_BOOTLOADER)\n        return S5E_RESET_EREASON;\n", ""),
    ("bootloader-mode-not-used", C, "return reason == S5E_REASON_BOOTLOADER ? S5E_MODE_FASTBOOT : S5E_MODE_NORMAL;", "return (void)reason, S5E_MODE_NORMAL;"),
    ("trigger-before-the-status-check", C, "    if (r != S5E_RESET_OK) return r;\n    s5e_reset_trigger(pmu);\n", "    s5e_reset_trigger(pmu);\n    if (r != S5E_RESET_OK) return r;\n"),
    ("wait-after-trigger-removed", C, "    S5E_WAIT();\n    return r;", "    return r;"),
    ("snapshot-clears-inform3", C, "out->inform3 = S5E_MMIO_R(pmu + S5E_PMU_INFORM3 / 4u);", "out->inform3 = S5E_MMIO_R(pmu + S5E_PMU_INFORM3 / 4u); S5E_MMIO_W((volatile uint32_t *)(pmu + S5E_PMU_INFORM3 / 4u), 0);"),
    ("trigger-value-wrong", H, "#define S5E_PMU_REBOOT_TRIGGER  0x2u", "#define S5E_PMU_REBOOT_TRIGGER  0x1u"),
    ("trigger-offset-is-the-legacy-0x400", H, "#define S5E_PMU_REBOOT          0x3c00u", "#define S5E_PMU_REBOOT          0x0400u"),
    ("inform3-offset-wrong", H, "#define S5E_PMU_INFORM3         0x00bcu", "#define S5E_PMU_INFORM3         0x00b4u"),
    ("inform2-offset-wrong", H, "#define S5E_PMU_INFORM2         0x00b8u", "#define S5E_PMU_INFORM2         0x00b4u"),
    ("cmd-offset-is-the-default-sysip-dat0", H, "#define S5E_PMU_REBOOT_CMD      0x0190u", "#define S5E_PMU_REBOOT_CMD      0x0810u"),
    ("download-value-wrong", H, "#define S5E_REASON_DOWNLOAD     0x12345601u", "#define S5E_REASON_DOWNLOAD     0x12345611u"),
    ("bootloader-value-wrong", H, "#define S5E_REASON_BOOTLOADER   0x1234560du", "#define S5E_REASON_BOOTLOADER   0x1234560eu"),
    ("normal-value-wrong", H, "#define S5E_REASON_NORMAL       0x12345600u", "#define S5E_REASON_NORMAL       0x12345610u"),
    ("inform2-magic-wrong", H, "#define S5E_INFORM2_NORMAL      0x4eu", "#define S5E_INFORM2_NORMAL      0x4fu"),
    ("fastboot-mode-wrong", H, "#define S5E_MODE_FASTBOOT       0x3u", "#define S5E_MODE_FASTBOOT       0x5u"),
]


def build_and_run(tree):
    exe = os.path.join(tree, "t")
    cc = subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", os.path.join(tree, "module"),
                         os.path.join(tree, "test", "host_test.c"), "-o", exe], capture_output=True, text=True)
    if cc.returncode != 0:
        return "invalid", cc.stderr[-300:]
    r = subprocess.run([exe], capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout[-300:]


def copy_tree(dst):
    for d in ("module", "test"):
        shutil.copytree(os.path.join(HERE, d), os.path.join(dst, d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=False)
    results, bad = [], 0
    with tempfile.TemporaryDirectory(prefix="nat042-mut-") as tmp:
        base = os.path.join(tmp, "base"); copy_tree(base)
        rc, out = build_and_run(base)
        results.append(dict(name="baseline", exit=rc))
        if rc != 0:
            print("baseline fails; refusing to judge mutants:", rc, out); return 2
        sources = {C: open(os.path.join(HERE, "module", C)).read(), H: open(os.path.join(HERE, "module", H)).read()}
        for i, (name, fname, old, new) in enumerate(MUTANTS):
            n = sources[fname].count(old)
            if n != 1:
                results.append(dict(name=name, status="anchor-mismatch", count=n)); bad += 1
                print("%-42s ANCHOR MISMATCH (%d)" % (name, n)); continue
            t = os.path.join(tmp, "m%02d" % i); copy_tree(t)
            with open(os.path.join(t, "module", fname), "w") as f:
                f.write(sources[fname].replace(old, new))
            rc, out = build_and_run(t)
            status = "invalid" if rc == "invalid" else ("killed" if rc != 0 else "SURVIVED")
            bad += 0 if status == "killed" else 1
            results.append(dict(name=name, status=status, exit=rc))
            print("%-42s %s" % (name, status))
    killed = sum(1 for r in results if r.get("status") == "killed")
    summary = dict(total=len(MUTANTS), killed=killed, not_killed=bad, results=results)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print("killed %d of %d" % (killed, len(MUTANTS)))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
