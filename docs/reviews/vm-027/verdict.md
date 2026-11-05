# REV-029 verdict — 2026-11-06

PASS for the bounded VM-027 parser and actual shim-tree capture contract through
250bce50945ab0c79235dabcd0bd355a44623d0d. No blocking finding within that scope.
Root acceptance and the serialized integration check remain pending; this review
does not close VM-027 or REV-029 by itself.

The independent review source is frozen at
a5c287f156389c23aafb960dfb85fd2a258553b1. The producer parser SHA256 is
84685695772d3eeb9e2d77fae6672ad75620d9edeb1b5cc7a69def2795074bcf and
capture runner SHA256 is
8320c105c6862f832491b3937089b405c1357a8954c7b1f6d7b12cbd94a29455.
The frozen producer capture capsule has SHA256
b92c3e281105c3bd76ad7ff54311028830500c038b3e706a2fc68b4f965e85d2.
The series adds the parser/source controls, preserves source-only evidence,
prepares capture and actual-byte controls, repairs post-spawn memory/SIGTERM
guards, then records actual capture. The final 250bce5 change contains only the
procedure README, handoff and capture capsule; executable changes end at 5d03516.

## Actual bytes and selected source contract

The input is the preserved 12,540-byte tree, SHA256
afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491.
An independently written iterative reader decoded all 14 nodes and 84 properties,
retained their original order/offsets, and reconstructed the identical input.
Every node path, property value/value offset, node offset and child count agrees
with the frozen parser. The actual input passes its 38 selected property checks.

The genuine pinned shim writer uses little-endian node counts and 32-byte property
names, a 32-bit length, value and zero alignment padding. It records the emitted
length in boot_args. The reviewed parser bounds total bytes, recursion, nodes and
properties, checks each read before advancing, and rejects ambiguous duplicate
names, trailing bytes and malformed strings/padding. These restrictions describe
the selected writer and deliberately exceed some kernel lookup restrictions;
they do not establish a universal Apple DT ABI.

All 22 pinned source files were checked by size, SHA256 and content Git blob ID.
Canonical Scion code bytes also match the pinned upstream commit. The local
promisor reference lacks the non-code THIRD_PARTY_LICENSES.md blob; its pinned
tree entry matches the cached file's computed Git blob ID. No lazy fetch occurred.
The composed kernel consumers are pinned composed source, without an assertion
that every composed file is an unchanged public-XNU blob. GIC source fixes the
virtual timer PPI at 27, independently of the emitted property; UART/PCI source
selects the accepted console/configuration variants.

The independently decoded actual mappings agree with the console and selected
launch: GICD 0x08000000, GICR 0x080a0000 with size 0x00f60000, PL011 UART
0x09000000, PCI configuration 0x4010000000+0x10000000 and buses 0..255. CPU0 is
running, logical/physical ID zero, HVC PSCI, timebase 1,000,000,000 Hz. RAMDisk is
absent. The preflight checks selected widths, required properties, nonzero and
nonwrapping extents, GIC/UART containment, GIC overlap, timer agreement, topology,
PCI record alignment and configuration coverage. It does not validate every PCI
range/interrupt record's semantics, all inter-region relationships, or runtime
driver behavior. Those are outside the stated selected-property preflight.

## Capture and cleanup audit

The actual report, plan2, runner, accepted supervisor and all eight tool/input/
build-record pins were rehashed. The capture console identifies the emitted tree
at 0x4300c000+0x30fc and boot_args at 0x4301c000. This differs from the separate
input QEMU FDT at 0x48200000. The recorded QMP requests are capabilities, stop,
query-status, pmemsave with that exact bounded address/length, and quit. The
query-status response confirms paused/running=false before saving; the transcript
records host-qmp-quit, exit 0 and zero remaining owned processes/RSS.

Source inspection confirms canonical fresh output checks, exact plan/input
revalidation, explicit lease verification, finite dump/console/reply/deadline
bounds, three stable admission samples, continuous memory/RSS guards and a
finally path for owned-session cleanup after SIGTERM. Actual capture took
3.153 seconds with peak aggregate owned RSS 52,047,872 bytes and stayed above the
4 GiB memory floor. The earlier draft plan and guard controls remain preserved;
the root's accepted capture controls were inspected, without replaying a guest.

## Independent execution and limits

Registered ADTREVIEW-001 before execution and verified its prospective owner/task
state before every child. Session2 passes 204 source/provenance checks across 66
input paths and 14 pinned Git reads. All 30 actual-derived malformed trees are
rejected: hostile counts/size, truncated/trailing data, name/value padding and
duplicate/path/depth ambiguity; platform/PSCI and overflowing DRAM/IO; GIC
overlap/bounds/timer; UART selection; CPU frequency/identity/state; and PCI
bus/configuration/record/probe contradictions. A well-formed unknown property is
preserved and leaves selected preflight unchanged.

The public CLI accepts the actual tree, rejects required RAMDisk when absent,
and rejects the separate input FDT. Executed exits are 0, 0, 2, 2; the expected
negative exit 2 is preserved as such. Maximum measured aggregate owned RSS is
47,693,824 bytes, all four jobs had stable >=4 GiB admission and no surviving
children. Commands, outputs, sample logs and hashes are retained in runs/session2.
The malformed binary fixtures stay local, bound by hashes and reproducible from
the original bytes and audit source.

Session1 remains an explicit failed reviewer attempt: upstream `git show` could
not read the locally absent notice blob. The reviewer changed only that identity
check to use the pinned tree entry and computed cached blob ID. All other checks
and the producer remained unchanged. Its failure is not a producer defect.

The captured tree was emitted by the genuine source-built shim running against
QEMU virt and an unchanged owned synthetic spin payload. No reviewer compiler,
guest, phone or common check ran. Generic console text saying “jumping to XNU”
does not establish XNU execution; the actual marker says SYNTHETIC SPIN-CONTROL.
This establishes neither XNU/PID1 execution nor RAMDisk/root consumption, native
kernel integration, private Apple compatibility, hardware compatibility or an
Exynos model. The old source-only capsule remains inconclusive.
