# BSD syscall generation attribution

KRN-012 introduces no upstream generator patch. Project-owned tooling queries
actual selected Make rules, invokes the genuine unifdef and makesyscalls.sh,
and records target object/dependency results in isolated paths. It supplies no
missing syscall declarations or manually constructed kernel tables.

The generator, master and Make rules come from Apple XNU8796.121.2 at
`c54f35ca767986246321eb901baf8f5ff7923f6a`, with the recorded E1S patch set.
Preserve APSL2.0 and all original per-file Apple/Berkeley/FreeBSD notices.
The script emits its original license notice into generated files; these remain
local ignored artifacts, outside Git.

Unifdef comes from the qualified HOSTGEN-002 source at
`08d12cd3059fe072929ea001ad9833f5487fd355`. Existing source/tool licenses and
notices remain unchanged. System sh/sed/awk/coreutils executables are measured
by hash; no global packages, headers, compilers or SDK contents are installed.
Owned layout fixtures and bounded Mach-O readers test real emitted data, without
executing ARM code or claiming Apple userspace/private syscall ABI equivalence.
