# Genuine top-level direct objects and setsegname

The selected XNU source base is c54f35ca767986246321eb901baf8f5ff7923f6a,
with previously recorded E1S preparation/donor patches. All four relevant
libsa/SETUP sources are copied unchanged from that base into isolated runs.
No kernel source patch is applied by this component.

host-compat.h is local MIT-licensed Linux-host glue. It includes genuine
cctools-port Mach host types and maps getprogname to glibc's diagnostic program
name. Public cctools-port headers are pinned to
904de2a71d4da6a9b30d2efaf912a10ddc7d9ddb; their existing APSL/per-file notices
remain unchanged. XNU's setsegname algorithm and its license notice are retained.

The original utility assumes well-formed Mach-O input. The runner validates
actual thin ARM64 command/section/symbol/relocation extents before executing it
and independently verifies that the output changes only intended section
segment names. The standalone binary is not qualified for arbitrary hostile
files. This is host tooling, with no SDK or private ABI substitution.
