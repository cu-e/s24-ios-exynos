# REV-024 resource-policy followup

The first actual MAIN common check failed after genuine fast-forward, leaving
4bea9b59d1d24c2f7f53f4028769b6e420be556e published. The unchanged lifecycle
Java test could not initialize javac under the gate's additional 2 GiB virtual
address-space cap. Root's javac -version control isolates that cap: exit 1 with
compressed-class-space reservation failure under the cap, exit 0 without it.
The user's limit concerns owned RSS. Preserve the original081cb62 review and
all first-publication failure evidence without rewriting its bounded verdict.

Review the integrator's exact minimal delta removing that virtual cap while
retaining two jobs, stable available-memory admission, sampled aggregate owned
RSS at 2 GiB, pressure/deadline stopping, descendant cleanup and the continuous
primary integration flock. Ensure no test skipping or JVM-specific adjustment.
Verify exact source/commit/capsule hashes. Register REVGATE-002 before executing
bounded fixture probes. A tiny fixture make may run javac -version only, under
the real common-check supervisor, to verify JVM initialization and lock ownership
with no source compilation. Also preserve exit-failure cleanup coverage.

No actual MAIN publication or project make check, source compiler, QEMU, phone,
ADB, SDK acquisition or unrelated-process termination. Wait for integrator fresh
MAIN common PASS before original-owner task completion.
