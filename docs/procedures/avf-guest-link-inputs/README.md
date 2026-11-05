# VM-022 guest archive and link preparation

Owner: codex-guest-exec-20261106-cu. Worktree: worktrees/vm-022-20261106;
branch: team/vm-022-20261106. This task prepares the actual public guest
ARM64/DEVELOPMENT/BCM2837 archive and image link contract.

AVFLINKPREP-001 runs only bounded GNU Make variable/rule queries against the
immutable VM-008 source and generated configurations. Each query has an empty
explicit target; no compiler, preprocessor, generator, archive tool, linker,
section processor, QEMU or device command runs. Inputs and output text use
streaming SHA256, and the process records /proc/self/status VmHWM separately
from inherited getrusage. Owned output is a fresh task-local artifact directory.

The preparation must preserve component order, OBJS versus LIBOBJS, HIB/KLD
transforms, top-level tail recipes, symbol exports/aliases and symbolset plist
rules. It must reject altered source/tool/config bindings and incorrect profile
selection. Linker, libtool and setsegname are reused only after exact prior
source-built descriptor hashes match. Native E1S objects and archives are not
guest inputs. No RELEASE-only exports flag may be imposed on DEVELOPMENT.

The prepared contract records unmeasured work explicitly. Actual guest objects,
external provider archives, fresh tail/version products, complete symbol closure,
archive members, final image layout, private Apple ABI and guest execution remain
unqualified until independently accepted component results and the required root
resource leases exist. Only integrators publish MAIN and run common checks under
state/.integration.lock; this task does neither.

AVFLINKTEXT-001 is a separate bounded source-text phase. It consumes the passing
source-query contract and runs only the genuine pinned export/alias shell scripts,
newvers.pl on owned copies, and the genuine nine symbolset/combined-plist scripts.
The final binary plist uses Python's documented standard plist representation and
a semantic roundtrip, without claiming qualification against Apple's plutil.
Fresh version.c is a generated source, never an object. All failed attempts remain
in new immutable run directories. This phase does not invoke any compiler,
preprocessor, linker, libtool, section processor, guest or device operation.

The first source-query experiment is inconclusive. Its initial index-key lookup
failed, and later passing order queries were superseded when a source audit found
that copying the osfmk command also copied osfmk CONFIG_DEFINES into other contexts.
AVFLINKPREP-002 corrects each component to its own exact doconf declaration and
uses the genuine empty inherited CONFIG_DEFINES for top-level/config queries.
Prior artifacts are retained and cannot qualify final tail compile templates.
