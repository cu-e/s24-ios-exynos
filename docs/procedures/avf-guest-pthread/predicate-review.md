# Frozen pthread plan predicate correction

Independent platform reviewer `codex-integrator-platform-20261106-cn` found
that the original `validate_plan` accepted removal of both `-DMACH_ASSERT`
and `-DDEBUG` from all three recipes. The actual emitted DEVELOPMENT recipes
at `e884676` / `f10dda9` contain both definitions and remain unchanged.

The corrected execution predicate checks the complete parsed plan against an
independently committed canonical SHA256 in `execution-plan-freeze.json`.
That pin comes from the original plan whose byte SHA256 is
`96065bf4ebe697cfd1a0d43eb52d0ae315275f25efe619e60ae14d66ae350298`.
It cannot be recomputed from the candidate being validated. Definitions,
their order, compiler, sources, output templates and all other plan fields
must remain exact. JSON object key order and formatting are immaterial.

`validate_preparation_plan` retains the existing structural source-generation
check. It is explicitly insufficient for execution. Fresh source preparation
does not automatically update the execution freeze; a new plan needs separate
review. A later execution adapter must validate the original template before
substituting `@OWNED_OUT@` only in its declared `-MF` and `-o` values. This
predicate itself accepts no argv substitutions or extra flags.

The `validate_plan` name is the frozen-plan gate. Callers must not substitute
the preparation-only helper for that gate. No execution adapter is implemented
or accepted by this correction.

Register AVFPTH-002 before the focused controls. The controls read only the
small original plan and local predicate/freeze files. They preserve the old
predicate's reproduced acceptance and test the unchanged plan, dropped real
development definitions, appended undefined/redefined development macros,
source/output redirection, response/forwarding flags and compiler replacement.
They never rehash sources/headers, compile, create an archive, run QEMU or
perform common checks/publication.

```sh
timeout 30s env LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  docs/procedures/avf-guest-pthread/predicate_controls.py \
  --plan artifacts/avf-guest-pthread/prepare-2/component-plan.json \
  --out artifacts/avf-guest-pthread/predicate-controls-1
```

The measured command exited 0 with 21 checks passing in 0.018132 seconds;
actual controller `/proc` VmHWM was 21,392 KiB. The Git-read historical predicate
at exact commit `f10dda9c713c7b6a1516ff77f9d62d8340205805` accepted the removed
development definitions, reproducing cn's finding. The corrected predicate
rejected that candidate and all targeted mutations. Original plan byte SHA256
remained identical before and after. The complete report is
`artifacts/avf-guest-pthread/predicate-controls-1/evidence.json`, SHA256
`c16f8c71f2ba6deaa8a57b7fa0e0d2eb80087646d08976b5bd9b23d9228ba803`.
No source/header rehash, source regeneration or compiler execution occurred.
Git child RSS was not sampled; the VmHWM value is the controller reading.
