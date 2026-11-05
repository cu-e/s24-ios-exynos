# Offline ARI parser corrections

Base: seemoo-lab/aristoteles `25cb9bb5c35993ed0c74248b96f0065d5479f447`. Main and nested libari LICENSE are MIT, copyright2021 Tobias Kröll. Preserve them with source/artifacts and any redistribution. The patch modifies libari only; no Apple binary or private trace is included.

0001 fixes four independently testable wire-analysis issues: split sequence high bits must come from byte8, a TLV payload ends at its start plus its declared length, the high TLV length byte shifts by six, and a complete packet must reject malformed/truncated extents. The source Lua dissector independently locates sequence high bits at byte8. Owned literals and boundary cases test the real Python donor before/after applying this patch in private copies.

0002 applies after0001. Actual pack-to-parse checks exposed a separate mismatch: Packet.pack returns bytearray, while TLV.setData treated its nonempty slice as a scalar. Copy bytes/bytearray/memoryview payloads into owned immutable bytes. Test retained data after mutation of caller storage and parsing of the actual bytearray output; do not evade the boundary by converting only the test input.

See [procedure and limitations](../../../docs/procedures/esim-profile/README.md). This is an offline analysis aid, not an ARI-to-Samsung modem bridge, selected iOS16.5 ABI qualification or native/eSIM provisioning result. No source watcher, injector, replay or live capture is executed. Encoder range/unknown-bit behavior outside the named cases remains unqualified.
