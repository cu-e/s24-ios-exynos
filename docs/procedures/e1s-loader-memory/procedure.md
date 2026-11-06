# E1S RAM ownership regression — STRMEM-001

Original STR002 owner codex-e1s-memory-20261106-sr2. Source baseline is actual
RNDMBG/iOS-On-S24 c886; all six selected source/header bodies are identical at
official57d0. Attributed GPL-2.0-only patch modifies only loader.c/fdt.c/fdt.h.
Pinned reference trees and tools/build/e1s.py remain unchanged.

Register this actual compile/control experiment before any compiler execution.
Preparation sessions1/2/3/4/5 already staged exact source/patch application and
prospective command JSON, without compiler or control execution. Earlier plans
remain unchanged but are unselected;5 is final after static fixture cleanup and
adding physical guard pages. No retrospective preregistration is claimed for
these source-only preparations.

Root admission is required for the six exact commands in prepare-5/plan.json:
serial original and patched host ASan+UBSan builds, actual-C controls, and two
AArch64 freestanding loader/fdt object compiles. One compiler/executor at a time,
256MiB RSS, >=4GiB stable admission,120s per command and600s whole. ASan requires
RSS-only supervision, no small RLIMIT_AS. Reuse accepted supervision/resource
admission; this task adds no executor. Save commands/exits/stdout/stderr and
actual /proc RSS/HWM/owned cleanup, source/tool/input/output hashes. Preserve
failures; no automatic retry, cap/tool/flag change, install or global repair.

The harness includes actual extracted loader selection functions and actual
whole fdt.c, not a Python reimplementation. Baseline uses six structurally
bounded DTBs that expose silent incomplete-map acceptance. Patched cases use
real FDT encoding in host guard-page-backed mappings and check supported gaps,
header reservation-map exclusion, declared block truncation/string/name bounds,
endpoint arithmetic, output capacity, unsupported translated/dynamic reservation
semantics, no-free-window failure and unchanged outputs on failure. The loader
callsite must return failure instead of payload phys/mem fallback. Target compile
uses unchanged existing builder C flags with this explicitly pinned compiler;
no full loader/kernel link, image pack, guest or hardware execution is implied.

The S-Boot ABI still must supply an accessible FDT header and declared readable
span. This patch bounds all traversal by validated declared blocks (maximum2MiB);
it cannot certify physical backing, firmware carve-outs or a measured safe RAM
window from source alone. Fixed log/framebuffer ownership and physical handoff
remain separate tasks. No phone/ADB/MMIO/root/flash/reboot or power action.

Root explicitly held unexecuted d090. Its exact owned patch/fixture/pins/checker
bytes are preserved in unexecuted-d090-snapshot before the board-policy delta.
Generic FDT empty-map parsing remains valid (returns0); E1S selection rejects0
reservations rather than asserting complete firmware ownership. Final35 patched
controls include both generic-empty acceptance and board-empty refusal. Source
preparation4 is also unexecuted/superseded;5 removed a fixture-only new-API call
so the same C harness still links against the genuine unmodified donor. No
compiler run, failed measurement or physical matrix repetition occurred.
