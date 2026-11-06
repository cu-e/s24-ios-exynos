# Additive inspector snapshot correction

Independent source review of commit 0ff8705fa1a88304c193ceaf8cedb3a002696c72
identified P2: product hashes were checked from paths, then ELF/Image were
reopened for parsing and reopened again for result hashes. Plan SHA verification
and JSON parsing also used different opens. A pathname replacement could make
the validated, parsed and reported content disagree. This is a source finding;
no runtime reproduction, controls or compiler invocation occurred.

The original commit, prepare-001 plan 5d329ff58a28a81bd116da592cdba32f431a14eab9fd0a66843e89c293639294
and source-preparation-evidence.json remain preserved. The new prepare-002 plan
supersedes only the prospective inspector admission and adds correction pins.
The production builder, hook, source controls and all 23 recorded vectors remain
unchanged. STR031BUILD-001 remains planned and requires root admission.

The inspector now captures plan/report/loader ELF/Image/object/start/loader
source bytes once per input through one regular-file descriptor, with at most
16 MiB per captured input. Seven retained snapshots have a combined content
bound of 112 MiB; transient source reads are separately bounded. Expected ELF
and Image product SHA/size refer to the same captured bytes passed to layout
inspection. Source witness hashes refer to the exact bytes used for stack,
ABI and exclusion controls. JSON, ELF, source parsing and result SHA/size all
use the respective immutable bytes. Other products and unparsed input tools
are streamed once with a planned-size limit; hash and count use that stream.
Tool input sizes have an additional 2 GiB ceiling. No second pathname stat is
used to establish a measured size.

These are content snapshot claims. No assertion is made that a pathname still
names those bytes after capture, so no current-path identity/recheck claim is
needed. Negative derivative hashes likewise come from their exact tested bytes.
The original builder report does not hash loader.c.o or itself; their captured
SHA/size are observed bindings, with report command/product checks and actual
object-to-linked relocation checks, rather than invented prior authentication.
No external object/report manifest, compiler MD or native execution is claimed.

The 8 source-hook cases and 12 invalid artifact/source cases remain prospective;
none ran during correction. Independent source review precedes the same future
root-admitted genuine build and inspection. Kernel0011/0012 fixed physical writes,
ownership, mapping, retrieval, persistence and native/recovery gates remain open.
