# AVFFH-001 bounded guest firehose build plan

Owner: `codex-guest-exec-20261106-cx`, original VM-020 claim. Planning only;
there is no execution approval in this document. Source freeze is commit
`27303145d33105170a6f9623240c5be0685675fc`, following independently reviewed
original source recipes at `76db6b216fcb03c0e2035d37760464acbaca89ca`.

The concrete command arrays and input descriptors are in
`bounded-plan-session1/plan.json`. The run directory is the fresh, currently
absent literal-owned path
`worktrees/vm-020-20261106/docs/procedures/avf-guest-firehose/execution-session1`.
The three compiles retain every frozen recipe token except the declared
`@OWNED_OUTPUT@` values for `-o` and `-MF`. The fourth command uses qualified
source-built cctools libtool with a frozen single-member filelist to produce
`libfirehose_kernel.a` from `provider.o` only. Both layout and interface probe
objects are excluded from the archive. A fifth compiler or source matrix is
outside this experiment.

All four commands are serial, each admitted through the reviewed common
process engine with at most one child, 120-second command deadline, and a
256 MiB aggregate RSS limit including the controller and all child descendants.
Three MemAvailable samples at least one second apart must each be at least
4 GiB; a drop below the floor, memory excess or deadline stops owned processes
and preserves inconclusive/failure evidence. The experiment's registered
600-second timeout records the overall plan; the common runner must implement
actual stop mechanisms. RSS and available memory remain unmeasured for these
real commands. Root must explicitly approve the final adapter and resource
lease after the current common boundary before any child starts.

The accepted VM009 `run_child` is a process engine, not a complete component
adapter. A reviewed adapter implementing task/owner/path and exact-argv
admission, source/configuration/namespace/tool/resource/runtime pins, finite
cleanup and artifact inspection is still missing. Its path/hash must be bound
by root's approval. This plan does not supply or duplicate that engine.

The Clang resource descriptor binds a source-built matched Clang17 resource
bundle and the CXX storage compiler's inherited `RHDR-002` provenance. These
firehose recipe arrays use `-nostdinc` and contain no `-resource-dir`,
`-idirafter`, resource include option or SDK invocation. The bundle is explicitly
bound as contextual provenance, not added to the accepted argv. Only accepted
public guest namespace headers and the fresh firehose export are supplied;
no Apple SDK is qualified or supplied. Any proposed resource flag change needs
separate source review and a new exact recipe freeze.

Read-only ELF metadata is preserved for compiler and archiver. Bind the actual
system runtime files and verify every ELF search candidate before execution.
The compiler's RUNPATH includes a literal backslash before `$ORIGIN` and an
empty search component; sanitized environment variables alone do not exclude
cwd library shadows. The planning observation checks named libraries in each
currently existing frozen cwd; it is not runtime-loader qualification. The
adapter must recheck absence of shadows in all effective RUNPATH candidates,
bind actual loaded host libraries, and preserve the selected search behavior.
No compiler, loader, `ldd`, archiver or QEMU is executed during planning.

After admitted execution, inspect actual ARM64 relocatables, depfiles and
read-only provider layout/interface records; require MAX_CPUS=8 and clusters=1
and report every actual size/offset without copying historical E1S values.
Check archive member/symbol tables and prove the archive contains only the
provider object plus normal symbol-table metadata. Genuine logging, kernel
link/boot and native phone behavior remain unqualified. Record actual four
commands, exits, timing, hashes, resource samples, partial outputs and failures
under AVFFH-001, then request independent review. Original owner retains task
and experiment recording; integrators alone publish MAIN and common checks.

Planning observations: AVFFH-001 was registered `planned` by the original
owner; registration returned exit 0 and did not execute tests. An initial
read-only plan attempt assumed `/usr/lib/x86_64-linux-gnu`, which is absent on
this host. That failure and its exact helper/partial outputs are retained in
`bounded-plan-session1-attempt1`. The corrected planner discovers actual
existing host-library path candidates without invoking a loader, and produced
`bounded-plan-session1/plan.json` with exit 0. The four compile/archive commands
remain unexecuted. The plan explicitly keeps runtime search resolution and the
reviewed component adapter as missing gates.

Raw `readelf` program-header output includes trailing section-map spaces.
The first formatting check reported those spaces; the scoped `.gitattributes`
rule preserves the exact evidence bytes while excluding only these raw stdout
files from whitespace diagnostics. Maintained code and prose retain checks.
