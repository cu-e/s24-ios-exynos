# CELL-009: matching Samsung vendor command input gap

> 2026-11-10 update: the input gap described below was closed by CELL-011 (read-only su copy, decision 0002), and the static analysis is in [README.md](README.md). This handoff is kept as the historical record.

2026-11-05. Owner `codex-ril-inputs-20261105-m`, main checkout. No matching binary was supplied or analyzed; this task cannot complete command-schema acceptance yet.

CELL-010 now provides actual evidence instead of an assumed missing file: exact SM-S921B/e1s/S921BXXS9BYH3 uid2000 context was verified before/after passive acquisition attempts. The phone has regular /vendor/lib64/libsec-ril.so5459848 bytes and /vendor/lib64/libsecril-client.so134368 bytes. Current shell SHA256 and ordinary ADB sync pull both return Permission denied. Source bytes/hashes/ELF identity remain unavailable. No root or access-control changes were requested. See state/evidence/RILINPUT-003.json and004 and docs/procedures/ril-capture/handoff.md.

Next required external input: an explicitly supplied matching local library or exact BYH3 vendor-image artifact, with source device/build/acquisition provenance and original hash. Record extraction tool/revision, source image and output digests before use. A file named libsec-ril.so, an older example from another device or generic S5000AP driver code is not a matching command schema. No automatic firmware archive download follows from this task.

The pinned [BaseMirror source](https://github.com/OSUSecLab/BaseMirror/tree/b210841cf9f04c72b0d64259d39bb656e77da543) is an offline static-analysis method, not a ready S24 driver. Its documented environment is Ubuntu20.04/OpenJDK11.0.2/Ghidra9.2.2 with at least32GB RAM/10GB disk. Current host checks show JDK/GraalVM25.0.1,29GiB total RAM/about7.9GiB available and no ghidraRun on PATH. This does not prove no installation exists elsewhere; no analyzer/toolchain was qualified or executed. Pin/isolate a reviewed compatible toolchain when actual inputs exist, rather than treating current JDK or generated strings as a successful extraction.

Then trace actual write/read sinks and command builders, request/reply/unsolicited mapping, transaction/slot ownership, bounds and payload schemas for SIM/APDU, registration, PDP/IP, SMS and IMS. Separate static inferences from independently supported field facts and unknown/dynamic fields; preserve unresolved cases. CPIF SIPC5/SIT framing and selected iOS frontend ABI remain separate protocols. Version only sanitized schema facts and provenance, never the proprietary input or private identifiers.

Exclude BaseMirror's automatic-testing subtree, rooting/install scripts, replay/device fuzzing, modem reset and profile operations. Unknown commands remain unsupported and are never transmitted to the daily phone. No actual command-schema, packet-data, call or eSIM support is established by this handoff. Continue independent host tasks while this concrete input gap remains.
