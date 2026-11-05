# Proposed bounded pthread compile and archive

AVFPTH-003 is a future four-command experiment owned by the original VM-021
owner `codex-guest-exec-20261106-cy`. Registration records a plan and grants no
permission to execute. No command from this plan has run. The component
execution adapter is missing; the reviewed process helper alone is insufficient
to enforce component provenance, ownership, substitutions or product validity.

The machine-readable plan is
`fixtures/public/avf-guest-pthread/compile-plan.json`. It keeps the independently
reviewed original three argv templates unchanged. A future reviewed adapter
must call `validate_plan` on the complete original template plan before
substituting only the declared `@OWNED_OUT@` values following `-MF` and `-o`.
All other compiler/source/include/definition tokens remain exact.

The fresh output and every command's explicit cwd are:

```text
/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-021-20261106/artifacts/avf-guest-pthread/compile-1
```

Planning does not create that directory. Three serial compiles produce
`kern_init.o/.d`, `kern_support.o/.d`, and `kern_synch.o/.d`. The fourth command
uses the qualified genuine source-built cctools libtool with
`-static -csD -filelist FILE -o`, the exact command form actually qualified in
MACHOTOOLS-004. The frozen `archive-members.filelist` contains exactly those
three fresh object paths, in that order, to produce
`libpthread_kext.a`. All expected product hashes remain null until measured.
An actual failed compile prevents later commands and is retained, not replaced
with an old E1S object/archive or an empty provider.

The process entrypoint is the physical primary
`tools/build/avf_kernel_objects.py`, SHA256
`5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8`, function
`run_child`, at the accepted MAIN `12a43eef` common boundary relayed by INT-003
from kernel integrator cm. Actual primary source bytes match that hash;
`run_child`'s AST matches the earlier reviewed physical VM-009 helper. The
historical physical worktree still has `132135...` and is not selected here.
Its source and supervisor hash must match this accepted boundary before any
lease. The missing component adapter is assigned separately to VM-036/dy.
Each command
uses timeout 120 seconds, admission enabled, three stable 4 GiB samples,
one compiler maximum, and combined controller/owned-process RSS at most 256 MiB.
The experiment's outer deadline is 720 seconds. Landlock must confine writes to
the fresh owned output. No secondary process engine is introduced.

The exact frozen compiler uses `-nostdinc`; no `-resource-dir`, resource include,
SDK or sysroot flag is added. The prior default driver resource path is recorded
as an observation only. The cc_kext resource-positive tree is link-only and
does not belong to these `-c` commands or archive construction. The source-made
installed guest headers and four public supplements retain their exact pinned
manifests. Actual transitive dependency membership must come from fresh `.d`
files; source preparation's prior checks do not establish that future result.

ELF metadata inspection, without running a compiler or loader, found a literal
backslash before `$ORIGIN` and a trailing empty component in the compiler's
RUNPATH. Thus a sanitized environment alone cannot establish runtime identity.
The future adapter must reject all needed-library shadows in its explicit cwd
and every relevant literal/expanded/empty RUNPATH directory before each command,
rehash pinned resolved host runtime candidates, and verify actual loaded image
and runtime libraries. The plan's `/usr/lib64` library hashes are inspected
candidates, not a claim that a loader executed or selected them. No `ldd` or
loader invocation was used during planning.

Before execution, independently review the actual component adapter, concrete
four-command plan, all input/runtime hashes, task/owner/worktree/output binding
and exact full-plan predicate. Obtain root's explicit heavy lease and stable
memory admission only afterward. Keep all failures and stop after the first
failure or resource deferral.

Post-run checks must establish actual ARM64 MH_OBJECT headers, real allocator
metadata sections, exact depfile target/source identity and dependency hashes,
and a genuine archive with exactly the three real members matching object
bytes. Full compiled callback ABI, type/size/offset agreement, allocator
descriptor semantics, real guest provider closure and alias relocation probes
remain additional acceptance gates. This experiment alone does not qualify
them, a full kernel, guest boot, Apple userspace or native hardware.
