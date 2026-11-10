# STR041LINK-001: one native E1S DEVELOPMENT link

Evidence category: host-test. This builds a Mach-O file on the Linux host. It does not boot,
package or qualify anything on hardware, and QEMU and the phone are not involved.

## Hypothesis

The 1042 qualified native bodies, the 22 metadata products, the provider archives and the tail
objects link once under the 512MiB serial budget into a fresh ARM64 MH_EXECUTE image that passes
the pinned segment and entry checks. Undefined private symbols, a resource violation or a failed
link refute this and stay recorded as failed evidence.

## Procedure

1. Run `native_link.py execute` on the frozen plan exactly once.
2. Limits: 1800s whole deadline, 120s per child, 512MiB owned RSS, one serial tool, external
   `/usr/bin/timeout` watchdog at most 1890s.
3. The heavy lease is self-issued by the Claude session acting as coordinator under the owner
   directive of 2026-11-10. The Codex root coordinator took no part.
4. No retry under this experiment ID. A second attempt needs a new experiment.

## What this cannot show

A successful link does not establish that the kernel boots, that private37 ABI obligations are met
or that `check_all_exports` passes. The native DEVELOPMENT driver has no RELEASE export-list flag,
so that check is not run.
