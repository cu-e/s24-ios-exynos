# Source-qualified UFS READ(10)/MCQ host boundary

This project-authored C11 boundary prepares byte records and tracks one DMA
lease. It performs no MMIO, mapping, cache operation, queue publication,
controller reset, write/erase/format command or storage data transfer. It is
preparation for DRV-002; its kernel dependencies and hardware gates remain.

`source-profile.json` pins exact E1S/Samsung inputs, hashes, licenses and
unavailable device inputs. The evidence oracle compiles genuine Samsung
UTRD/CQE/PRDT/UPIU declarations and the actual E1S pure command builder, with
only explicit host type/endian/capture adapters. Full original source and
notices remain in ignored evidence. No full vendor or donor implementation is
added to tracked code. No blanket E1S redistribution grant is inferred.

The strict admitted profile is READ(10), device-to-host, ten CDB bytes, flags/
group/control zero, nonzero count, and exact expected byte count. Unknown
opcodes, host-to-device/no-data directions, ancillary READ flags and zero
counts are rejected. This is a restricted profile, not general SCSI support.
Standard LUN 0..127 is admitted only under a caller-qualified policy; RPMB and
other well-known LUNs are excluded. Block size 512 or 4096, capacity and selected
partition extent must be supplied from independently qualified metadata.
This boundary does not parse GPT, choose partitions or authorize a LUN.

All LBA/count/extent tests use subtraction before addition. READ(10) cannot
cross the uint32 LBA limit. Transfers are bounded to 1 MiB with at most four
256 KiB PRDT chunks. PRDT DBC is bytes-minus-one. UTRD/CQE/PRDT fields are
little endian; multi-byte UPIU fields are big endian. Caller-qualified UCD
and data DMA regions must be aligned, disjoint, sufficiently large and not
wrap uint64. No physical address is probed and no IOMMU authority is inferred.

UTRD and CQE are 32 bytes. Response and PRDT lengths occupy the lower 16 bits
of their DWORD, offsets the upper 16 bits; offsets/response length use DWORDs.
The owned profile uses 512-byte command and response slots and four 16-byte
PRDT entries (1088 UCD bytes). Samsung MCQ defines UCD address in bits 63:7,
SQ ID in 4:0 and reserved bits 6:5. The donor uses a single UCD at a 4096-byte
offset. The 1088-byte donor UCD is not a 128-aligned array stride: future pooled
UCD layouts must use the actual Samsung padded allocation rules, not multiply
this packet size to recover tags.

Use fresh/retired storage for init. Prepare while idle, then call
`ufs_host_reserve_device` before cache/DMA setup and hardware publication.
A nonzero return forbids publication. Success reserves the lease; even a
subsequent backend publication failure cannot logically cancel it. The backend
must serialize calls and prevent interrupt completion racing reservation.
`ufs_host_cancel_prepared` is permitted only before device reservation.

Completion requires matching software epoch/generation, CQE UCD/SQ ID and
on-wire UPIU LUN/tag. A software token is not present in the MCQ wire record.
Task tags never wrap within a lease: retire after 255 preparations. Across
initialization/epoch changes, a real backend must quiesce and drain old queues
and establish DMA ownership before reuse; logical epochs alone cannot detect
an old same-address/same-tag completion. Never reinitialize active storage.

The strict success response requires no OCS error, response/status error,
underflow/overflow/other flags, residual, sense, extra header or data segment.
Unsupported notifications are rejected rather than treated as complete data.
Malformed/truncated or mismatched completion never releases DMA ownership.
Matching errors and timeouts quarantine the lease. No recovery/reset API or
automatic retry/reuse is provided. Successful validation enters COMPLETE;
only a separate `ufs_host_reclaim` call, after the backend has consumed the
completion and actually returned/cache-synchronized DMA to the CPU, admits
another request. The caller supplies monotonic nanoseconds and bounded timeout.
No logical state proves hardware quiescence or safe Android continuation.

The donor checks low OCS and response type/result/status, but does not qualify
all CQE address/SQ/LUN/tag/residual conditions enforced here. Passing host
comparisons validates record interpretation, not donor hardware correctness.
BYH3 S9 source matching, PHY/IOMMU/MCQ/controller handoff, DMA coherency,
physical completion, native kernel linkage/execution and encrypted userdata
access remain unverified. A RAM root remains the independent early-boot path.
