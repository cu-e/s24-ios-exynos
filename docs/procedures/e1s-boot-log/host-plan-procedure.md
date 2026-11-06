# Prospective actual-function host controls

This is preparation only while STR-019 source proposal is independently reviewed.
Original packet20fe637/capsuleb9f8cc26/patch56966307 remains immutable. Preparation
may copy/hash owned source and write a fresh exact plan. It must not invoke a
compiler, fixture binary, sanitizer control, target tool, QEMU or device.

host-prepare.py binds the unchanged source packet, extracts the real loader
record/ABI declarations/logging/extent functions without changing their bytes,
and derives literal C cases from the independent arbitrary-precision vectors.
It copies only the source snapshot needed by a future full loader object.
The host harness is separate from the production overlay and introduces no
new runtime or controller. The existing pinned upstream decoder is the oracle.

The prospective plan reuses accepted framebuffer qualified NDK18 host compiler,
resource directory and four GNU sanitizer runtimes byte-for-byte. Preparation
hashes these files; it does not execute them or requalify the runtime. It also
pins actual source/fixture/decoder inputs. Genuine future compiler MD closure,
actual commands/exits/stderr, resource supervision and zero survivors must be
retained after execution. Missing or changed inputs are not silently replaced.

Future commands, only after independent source review and separate root budget:
compile one actual-function host C harness with ASan+UBSan and genuine MD;
run normal initialization/text/bounds/lifetime/extent/ABI controls and write two
actual record byte images; run the real upstream decoder against them; run the
same harness in separate deliberate ASan and UBSan negative modes with expected
nonzero exits and required distinct sanitizer diagnostics. Expected failures
must retain raw exits/stderr and cannot be treated as a generic test pass.

No framebuffer routines are executed. No target compile/link is included in this
host-only plan; genuine .data.bootlog target layout, image payload placement and
relocation reachability still require later reviewed target commands. The
source proposal's numerical extent calculation is not a physical mapping test.

Resource request (not an authorization): one job, child timeout120 seconds,
whole timeout600 seconds, owned child-tree RSS256MiB using the existing root
qualified RSS supervisor. Sanitizers require RSS supervision and no small
RLIMIT_AS. No new generic/parallel execution framework is added. The source
review registry kind cannot receive host-test evidence; root must resolve the
separate host-task/card boundary before registering an actual host experiment.
