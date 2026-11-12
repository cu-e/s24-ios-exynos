#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-075: mutation run over the analyser's readings and pass rule (analyze_nat075.py) and over the derivation (derive.py), against test_nat075.py.
Each mutant edits one literal in a temporary copy of this directory (the rest of the repository is linked) and test_nat075.py must fail.
A mutant that survives is listed, not hidden.

  artifacts/recovery-rescue-20261110-01/venv/bin/python -W ignore -I docs/procedures/nat-075/mutants_nat075.py --json PATH [--only NAME]...

Patterns are the SOURCE text of the .py files."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
AN, DE = "analyze_nat075.py", "derive.py"
M = [
    ("md1-size-not-checked", AN, 'd["name"] == "md1" and d["size"] == RESERVE', 'd["name"] == "md1"'),
    ("md1-name-not-checked", AN, 'd["name"] == "md1" and d["size"] == RESERVE', 'd["size"] == RESERVE'),
    ("md-size-read-from-the-wrong-field", AN, "size=int(m.group(5), 16)", "size=int(m.group(3), 16)"),
    ("page-size-tolerance-open", AN, "<= WINDOW // 50", "<= WINDOW"),
    ("page-size-4k-only", AN, "for size in (4096, 16384):", "for size in (4096,):"),
    ("page-size-16k-only", AN, "for size in (4096, 16384):", "for size in (16384,):"),
    ("vm-total-omits-wired", AN, "total = free + wired", "total = free"),
    ("cap-window-opens-early", AN, "CAP_RETURN = (165.0, 195.0)", "CAP_RETURN = (100.0, 195.0)"),
    ("cap-window-closes-late", AN, "CAP_RETURN = (165.0, 195.0)", "CAP_RETURN = (165.0, 260.0)"),
    ("cap-window-too-narrow-low", AN, "CAP_RETURN = (165.0, 195.0)", "CAP_RETURN = (176.0, 195.0)"),
    ("cap-window-too-narrow-high", AN, "CAP_RETURN = (165.0, 195.0)", "CAP_RETURN = (165.0, 176.0)"),
    ("cap-baseline-return-wrong", AN, "BASELINE_RETURN_S, BASELINE_DEADLINE_S = 87.72, 60", "BASELINE_RETURN_S, BASELINE_DEADLINE_S = 57.2, 60"),
    ("cap-baseline-deadline-wrong", AN, "BASELINE_RETURN_S, BASELINE_DEADLINE_S = 87.72, 60", "BASELINE_RETURN_S, BASELINE_DEADLINE_S = 87.72, 30"),
    ("upload-window-from-the-wrong-constant", AN, "ar.BASELINE_UPLOAD_S - ar.BASELINE_TOLERANCE_S, ar.BASELINE_UPLOAD_S + ar.BASELINE_TOLERANCE_S", "ar.BASELINE_UPLOAD_S - ar.BASELINE_TOLERANCE_S, ar.BASELINE_UPLOAD_S + 3 * ar.BASELINE_TOLERANCE_S"),
    ("upload-treated-as-download", AN, 'if klass == "download":', 'if klass in ("download", "upload"):'),
    ("upload-never-watchdog", AN, 'cls = "watchdog-upload" if lo <= dt <= hi else "upload-other"', 'cls = "upload-other"'),
    ("download-early-reported-late", AN, '"download-other-early" if dt < CAP_RETURN[0] else "download-other-late"', '"download-other-late"'),
    ("no-return-not-reported", AN, 'return dict(klass=None, dt=None, cls="no-return-seen")', 'return dict(klass=None, dt=None, cls="cap-reset")'),
    ("rule-ignores-chain-verdict", AN, 'chain_pass=verdict == "PASS"', "chain_pass=True"),
    ("rule-ignores-probe", AN, 'probe_ran=root_outcome == "probe-ran-to-exit"', "probe_ran=True"),
    ("rule-ignores-md1", AN, 'root_outcome == "probe-ran-to-exit", md1_ok=md1_ok, cap_reset', 'root_outcome == "probe-ran-to-exit", md1_ok=True, cap_reset'),
    ("rule-ignores-return", AN, 'cap_reset=ret["cls"] == "cap-reset"', "cap_reset=True"),
    ("rule-any-instead-of-all", AN, 'rule["pass"] = all(rule.values())', 'rule["pass"] = any(rule.values())'),
    ("rule-requires-page-size", AN, 'rule["pass"] = all(rule.values())', 'rule["pass"] = all(rule.values()) and read_vm(text)["page_size"] == 4096'),
    ("analysis-keeps-nat065-name", AN, "    A65.IMAGE = IMAGE\n", "    pass\n"),
    ("analysis-name-not-restored", AN, "        A65.IMAGE = old\n    texts", "        pass\n    texts"),
    ("reading-uses-first-text-only", AN, 'text = "\\n".join(texts[k] for k in sorted(texts)) if texts else ""', 'text = texts[sorted(texts)[0]] if texts else ""'),
    ("reading-omitted-from-output", AN, 'out["bigwin"] = readings(', '_unused = readings('),
    ("loader-window-size-from-base", AN, 'window_size=int(w.group(3), 16) if w else None', 'window_size=int(w.group(2), 16) if w else None'),
    ("loader-window-not-compared", AN, "window_ok=bool(w) and int(w.group(3), 16) == WINDOW", "window_ok=bool(w)"),
    ("loader-first-zero-value", AN, "zero_bytes_final=zs[-1] if zs else None", "zero_bytes_final=zs[0] if zs else None"),
    ("loader-zero-expectation-wrong", AN, "EXPECT_ZERO_BYTES = 146259968", "EXPECT_ZERO_BYTES = 0x100000000"),
    ("loader-clean-span-end-minus-end", AN, "span = int(ce.group(1), 16) - int(cb.group(1), 16)", "span = int(ce.group(1), 16) - int(ce.group(1), 16)"),
    ("loader-refusal-text-dropped", AN, 'REFUSALS = ("does not fit", "bad payload header")', 'REFUSALS = ("does not fit",)'),
    ("loader-reading-not-attached", AN, 'out["bigwin"]["loader"] = read_loader(lines)', 'out["bigwin"]["loader"] = read_loader([])'),
    # derivation
    ("derive-reuses-nat067-marker", DE, 'sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-075/native-attempt-%s-used.json")',
     'sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-067/native-attempt-%s-used.json")'),
    ("derive-keeps-nat067-glob", DE, 'sub(t, "*-nat067-%s-single-run-*.md", "*-nat075-%s-single-run-*.md")', 'sub(t, "*-nat067-%s-single-run-*.md", "*-nat067-%s-single-run-*.md")'),
    ("derive-prerequisites-not-extended", DE, "'NAT-065','NAT-066','NAT-067','NAT-068','NAT-074')", "'NAT-065','NAT-066','NAT-067')"),
    ("derive-keeps-nat067-package", DE, 'sub(t, "artifacts/nat-067/package-001", "artifacts/nat-075/package-001")', 'sub(t, "artifacts/nat-067/package-001", "artifacts/nat-067/package-001")'),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--only", action="append", default=[])
    a = ap.parse_args()
    results = []
    for name, fname, old, new in M:
        if a.only and name not in a.only:
            continue
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
            t = Path(t)
            for entry in ROOT.iterdir():
                if entry.name == ".git":
                    continue
                if entry.name == "docs":
                    (t / "docs").mkdir()
                    for sub in entry.iterdir():
                        if sub.name == "procedures":
                            (t / "docs/procedures").mkdir()
                            for proc in sub.iterdir():
                                if proc.name != "nat-075":
                                    os.symlink(proc, t / "docs/procedures" / proc.name)
                        else:
                            os.symlink(sub, t / "docs" / sub.name)
                else:
                    os.symlink(entry, t / entry.name)
            d = t / "docs/procedures/nat-075"
            d.mkdir()
            for f in HERE.glob("*.py"):
                (d / f.name).write_text(f.read_text())
            src = (d / fname).read_text()
            if src.count(old) != 1:
                results.append(dict(mutant=name, outcome="invalid", reason=f"pattern found {src.count(old)} times in {fname}"))
                print(name, "invalid", flush=True)
                continue
            (d / fname).write_text(src.replace(old, new))
            r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(d / "test_nat075.py")], capture_output=True, text=True, cwd=t)
            outcome = "SURVIVED" if r.returncode == 0 else "killed"
            tail = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:", "AssertionError", "SystemExit"))][:3]
            results.append(dict(mutant=name, file=fname, outcome=outcome, exit=r.returncode, first_failures=tail))
            print(name, outcome, flush=True)
    summary = {k: sum(1 for r in results if r["outcome"] == k) for k in ("killed", "SURVIVED", "invalid")}
    a.json.write_text(json.dumps(dict(summary=summary, results=results), indent=1) + "\n")
    print(json.dumps(summary))
    return 1 if summary["SURVIVED"] or summary["invalid"] else 0


if __name__ == "__main__":
    sys.exit(main())
