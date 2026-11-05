# Explicit E1S dependency profile

Base: oosexgang/hakios-xnu-kernel d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c. Preserve its APSL/component notices; no project license overrides them.

0001 changes the stock-Clang wrapper to require explicit absolute executable S24_XNU_CLANG/S24_XNU_CLANGXX paths. It retains the donor's other target/diagnostic/type-builtin behavior; this is not a claim of complete Apple compiler equivalence. No global /usr/bin/clang link is created.

The firehose and pthread compilation defines select E1S, and their stage2 entry requires explicit MACHINE=E1S. No BCM2837 fallback is accepted for this selected port. The current source-only firehose experiment independently measures both profiles for comparison: implementation objects are byte-identical and the seven measured structure/offset values agree; CPU/cluster counts differ. Thus the macro mismatch is not presented as already-proven corruption of this library.

Apply only in a new artifacts copy of the exact donor. Never run its setup/install stages automatically. A compiler-wrapper fixture may verify explicit-path failures and actual arm64 Mach-O C/C++ output; static patch review does not qualify the complete setup/pthread workflow. Actual pthread/archive/SDK and DriverKit integration remain KRN-003/KRN-001 requirements.
