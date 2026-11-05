# REVPID1-001: independent owned PID1 artifact and ABI review

Owner codex-review-pid1-20261106-ds, task REV-026. No implementation edits,
compiler, linker, guest, device, whole common checks or MAIN source writes.

Bind exact VM034 commits/source/source-plan/tools and raw five-command capsule
01488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2.
Review genuine selected XNU syscall register/trap/return/carry/memory semantics,
optimized IR/assembly and six executable SVC sites, conditional identity marker
and finite positive-progress write loops. Independently parse real Mach-O object
and executable extents, ARM64_ALL/MH_EXECUTE/LC_UNIXTHREAD/entry, 16KiB mappings,
4GiB pagezero, absent dyld/imports/undefined symbols. Check actual cleanup and
hashes without replaying builds or claiming runtime PID1/stack/ABI execution.

After registering this plan, run bounded in-process byte/source rejection controls
against copied bytes and a reviewer parser. Include trap immediate, carry capture,
identity marker/dataflow/source register constraints, image header/load-command/
thread/entry/segment/import/truncation changes. No producer implementation import
or compiler invocation is needed. Host Python only, current-image RSS <=256MiB;
finite timeout<=120s. Exact candidate path/SHA and descriptor are handoff outputs,
not a kernel execution or real PID1 claim. Keep task in progress for root
integration/common acceptance, then original reviewer owner alone closes.
