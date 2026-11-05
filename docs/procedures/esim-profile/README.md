# Selected iOS 16.5 eSIM frontend investigation

ESIM-004 retains iPhone X/iOS16.5 as the selected initial profile. It does not authorize obtaining Apple binaries, changing phone identity, installing code or operating subscriptions. A local SDK alone would not provide the actual CommCenter/frontend image.

No actual local iOS image/components or identity manifest were supplied to this task. Thus frontend presence, entitlements, daemon/plugin matching and IOKit ABI remain unknown. Public hardware requirements identify a gap: [Apple's eSIM requirements](https://support.apple.com/en-us/109317) begin with XS/XR, whereas the original iPhone X profile has nano-SIM. This does not establish that source adaptation is impossible or that a particular image lacks every relevant software component.

Apple's public [CTCellularPlanProvisioning documentation](https://developer.apple.com/documentation/coretelephony/ctcellularplanprovisioning) describes a carrier-app entry point with the CommCenter fine-grained public-cellular-plan entitlement. A public API declaration is not a system LPA, carrier authorization or selected-image implementation. Current documentation also contains later APIs; it cannot alone establish iOS16.5 availability or private ABI.

The pinned [ARIstoteles source](https://github.com/seemoo-lab/aristoteles/tree/25cb9bb5c35993ed0c74248b96f0065d5479f447) provides an additional Intel ARI/CommCenter dissection and libARI structure-extraction method. Qualcomm QMI and Intel ARI are separate candidates until the exact selected image/identity is inspected. Neither is Samsung CPIF/SIT or SIPC5. Packet management, raw-IP transport and call audio remain distinct boundaries. No ARI field table is promoted to a Samsung command schema.

At this pin README advertises extracted iOS18.3.1 information, while CHANGELOG also describes newer unreleased iOS27.0/24A435 structures and Ghidra12.1.4 changes. Preserve the discrepancy; neither source states that these tables qualify iOS16.5. The extractor depends on libARI symbol/data layout and mutates its Ghidra analysis database. It was inspected, not executed. Pin and validate a compatible isolated analyzer only after actual local inputs exist; no Frida/live hooks or replay are part of this work.

## Offline donor parser checks

Read main/nested MIT licenses and the exact source before execution. The checker verifies the pin and clean source, copies it into a new ignored run, and imports only the inspected pure-Python libari packet package. Binary crash/capture samples, injection/replay/watchers and installers are excluded from the checkout and execution.

Register ESIMARI-001 before the first command. It exercises the unchanged donor; actual failure is retained. The independent literal packet has two nonempty TLVs, group5, sequence0x5a7, message0x155, transaction0x1234 and15 payload bytes. It contains invented bytes, no live command/capture or subscription identifier. Additional cases cover every truncated prefix, invalid magic/declared extent, partial TLV headers/payloads and TLV length boundaries0/1/63/64/255/256/16383. Two original empty-payload upstream smoke tests run as well.

```sh
python3 tools/sources.py verify aristoteles
python3 tools/research/esim-profile/check_ari.py --run ari-original-session1
```

Register ESIMARI-002 before the corrected run:

```sh
python3 tools/research/esim-profile/check_ari.py --run ari-patched-session1 --apply-patch
```

The attributed patch is applied only to the run's copy. It corrects the packet sequence byte, nonempty TLV slice, high TLV length bits and strict complete-packet bounds. It is not a streaming parser or a general validated serializer; untested flags/range handling remain unqualified. Passing these owned cases improves offline analysis reliability but does not inspect an actual iOS16.5 image, implement eSIM provisioning or qualify the native port.

ESIMARI-001 retained the original failures (30 failures,8 errors; two original smoke tests pass). ESIMARI-002 applied0001 and passed the independent literal and malformed extents, but six real pack-to-parse cases failed because the donor rejects nonempty bytearray payload slices. Retain both reports and the original patch bytes. Register ESIMARI-003 before `--run ari-patched-session2 --apply-patch`: it applies0001 then0002 and also checks mutable-buffer ownership. Actual supplied-image compatibility remains unknown even if these seven offline test groups pass.

## Inputs required to resume selected-image qualification

1. Explicit local path plus acquisition provenance, selected iOS16.5 build/product identity and original manifest digests. Inspect immutable files; no automatic firmware/image download or extraction script execution.
2. Actual CommCenter, CoreTelephony/baseband interface and relevant image-specific plugin/library inputs, including matching libARI when that interface is present. Establish which components are standalone versus inside a shared cache. Record extraction tool/revision, source cache/image and output hashes. Do not guess paths or equate missing standalone files with absence.
3. Actual relevant entitlements, dependencies, interfaces, service matching and frontend capability evidence from that same image. Presence of a class/string or an eSIM Settings page alone is insufficient. Inspect the selected API/private ABI before implementing adapters.
4. Record a concrete adaptation decision: retain the first image and implement a matching frontend/backend, or propose an explicitly reviewed later eSIM-capable profile as a separate change. No automatic OS/profile switch follows from this research.
5. Native acceptance remains separately gated on real Samsung logical-channel/APDU transport, agreed test subscription, carrier/LPA behavior, Stop/timeout cleanup and recovery. Existing daily production profiles are not fixtures.

No supplied Apple components means ESIM-004 cannot complete its acceptance. Independent ESIM-001 transport/library preparation can proceed without claiming selected frontend compatibility.

Changing to an XS/XR/A12-capable image also introduces an architecture/PAC qualification question: [Apple documents arm64e support](https://developer.apple.com/documentation/security/preparing-your-app-to-work-with-pointer-authentication) for these devices, and [Clang documents arm64e as a specific ABI](https://clang.llvm.org/docs/PointerAuthentication.html). This is another reason to inspect actual image architecture, loader and kernel interfaces rather than treat a profile-name change as compatibility. No S24 PAC execution is measured here.

The fresh targeted Reddit search coverage is [recorded separately](../../../fixtures/public/esim-profile/research-coverage.json). Its combined response contained unrelated consumer-phone discussions; only titles/snippets were screened. It adds no reviewed post bodies to the old archive, recovers no unavailable code and does not prove absence of an implementation. Technical decisions above rely on pinned source and primary documentation.
