# KRN-043 — canonical export-checked E1S kernel and KPI set (not run yet)

The tool `tools/build/e1s_kernel_exports.py` is written but **has never been executed**. At 2026-11-10 ~07:3xZ, the Claude Code auto-mode classifier denied `python3 -I tools/build/e1s_kernel_exports.py --run canon-a` ("Code from External"). Following the owner's rule, no other way to run it was tried.

What the tool does, for any owner who resumes the task:
- It reuses the KRN-041 helpers from `docs/procedures/krn-041/missing_exports.py` unchanged.
- It compiles the 0001-patched native `pmap.c` under the STR-023 recipe. The only added flag is `-ffile-prefix-map=RUN=/krn043`.
- It relinks the STR-041 link with that object and applies the 0002 export profile.
- It runs the genuine kextsymboltool: both check_all_exports passes and all seven symbol sets.
- It publishes the kernel, export lists, `all-kpi.exp`, the symbol sets and `manifest.json` under `artifacts/e1s-kernel-exports/RUN/kpi-set`.
- `--compare` checks that two runs published identical bytes.

To resume: the owner allows the command in Claude Code permissions or runs it with `! python3 -I tools/build/e1s_kernel_exports.py --run canon-a`, then again with `--run canon-b`, then with `--run canon-a --compare canon-b`.
