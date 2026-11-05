# Selected kernel declaration ports

These two project-authored patches apply to the exact prepared E1S source,
Apple XNU c54f35ca767986246321eb901baf8f5ff7923f6a plus s24-port donor
c8860decc62c6d6180e609036d027a2997972420 and its recorded preparation fixes.
Both affected translation units originate in donor xnu/hackios/files.

The first removes an exactly redundant printf declaration after genuine kernel
headers already supply its prototype and configured function-like macro. The
second copies the exact opaque proc_pid bridge declaration from selected
osfmk/kern/task.c, matching the BSD sys/proc.h API without importing incompatible
Mach/BSD system typedefs. No replacement prototype,
crypto callback, algorithm, security setting or runtime tracing logic is added.
The genuine neighboring minicrypto.h is copied unchanged to preserve quoted
include lookup when compiling the isolated source copy.

Preserve selected Apple/donor APSL2 and all per-file/component notices. The
license text here uses repository LF endings; original measured license/source
bytes remain unchanged. This attribution does not override distinct component
notices or grant Apple SDK/private binary rights. Full crypto, private ABI and
native operation remain unqualified; unsupported crypto callbacks remain NULL.
