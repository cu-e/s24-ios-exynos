# GPU-012 source and compile-plan inspection

Hypothesis: a real typed IOUserClient/provider ingress draft can bind its API
declarations and planned target commands to the accepted public guest context
without executing a compiler, inventing Apple interfaces or advertising an
unready GPU backend.

Run `prepare.py` to a new owned artifact directory. Verify exact pinned manifest,
genuine recipe/source/configuration/header witnesses, unchanged SGPU dispatcher
and owned source hashes. Run `source-hash` and `wrong-target` in-memory negative
controls to separate rejection directories; each must exit 2 with its expected
specific reason. Record actual commands, exits, elapsed time and `/proc` high
water marks. Keep unsuccessful attempts unchanged.

Do not execute the planned C/C++ commands or authored host policy fixtures in
this experiment. They need their own registered plan, independent review,
explicit root lease/shared-budget admission and finite supervised processes.
Typed overrides, Mach-O symbols/imports/allocator metadata and ASan/UBSan are
unmeasured until those future actual commands run. No QEMU or phone operation.
