# Additive VM044 findings

## R2: pre-child resource-admission exception can dispatch later compiler rows

Priority P1. Confirmed in source freeze `2bb96f520791fb5dd5e05090fcffeabccc1a9e2d9e37dd0911221dce494a4f83` (b78b181 + 0e6678d), with a retained actual AF193 witness. Root identified the operative continuation consequence after reviewer EQ flagged the misleading resource dimension. Author EP confirmed the finding before final acceptance.

The real VM012 raw capsule `0017266ad8d6fb9ede3e38d189298f9ba37ed62b8ab87e97ad9317eecbc79402` contains object index 7, `bsd/ether_if_module.o`, generic validation_error `ValueError('Project budget lock acquisition timed out')`. Its object record SHA256 is `57edc6cca01718b80d1600efc3459240f66ff102d3594eef44f125e51059ecca`. Later rows remain in the same run, including actual compiler-child launches. This evidence is not replayed or relabeled.

In 2bb, stable_memory or the initial project_before budget.sample may raise before run_child creates a record. main catches that exception as an ordinary item failure/validation_error. No nonpassing item resource_qualification is set, the top resource dimension retains its initial pass, and the loop break condition does not match the generic fail. A later compiler row can therefore be dispatched after resource admission was lost, even though the whole run eventually fails.

Requested minimal correction: classify admission exceptions into an explicit record with child_started=false, a nonpassing resource dimension and no invented sample. The existing resource break must stop subsequent compiler dispatch. Preserve ordinary source-validation errors as their own behavior; do not broadly turn every validation failure into a resource failure. EP will preserve the physical 2bb source and producer003 measurement in a separate correction worktree. This record/stop fix does not justify rerunning the timing benchmark.
