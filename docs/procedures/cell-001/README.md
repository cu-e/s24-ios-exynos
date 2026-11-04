# CELL-001: Samsung CPIF boundaries and next implementation

The target is SM-S921B/e1s, firmware S921BXXS9BYH3. [Machine-readable contract](../../../src/platform/cellular/contracts/transport.json) and [host framing model](../../../src/platform/cellular/contracts/README.md) are preparatory work. No phone operation is part of this task. Original capture/source digests are in [Samsung inputs](../../../fixtures/public/radio-research/samsung-inputs.json).

## Required layers

```text
iOS 16.5 CommCenter / CoreTelephony / selected eSIM frontend
 -> matching IOKit services, selectors, channels and asynchronous messages
 -> Samsung vendor request/reply/event schema, transaction and slot ownership
 -> explicitly selected CPIF framing + SBD/shared-memory + PKTPROC data path
 -> verified reserved memory, coherency, mailbox/IRQ, clocks and secure boot
 -> matching signed CP firmware -> SIM/eUICC and cellular network
```

CPIF transport, vendor RIL messages and the iOS-facing ABI are three separate protocols. QcomBaseband's QMUX/QMI/QRTR/IPA path does not turn into Samsung CPIF by renaming functions. Its bounded queues, user-client design and eSIM session cleanup are references; Samsung startup, commands and packet plumbing need their own implementation.

| Stage | Required input and acceptance | Project task |
|---|---|---|
| CP boot | Exact shared-memory reservations and queue geometry, mailbox/IRQ, clock/PMU and secure-monitor ABI; signed matching firmware and startup completion. Stop on failed verification; retain original NV/calibration state. | CELL-002, then gated CELL-003 |
| Control transport | Verify `mif,protocol`, channel IDs, SBD capabilities, finite queue ownership and error/reset teardown. The host model alone supplies none of those runtime facts. | CELL-002 |
| Vendor commands | Identify matching RIL binary/version and sanitized request/reply/event schemas. Pair transaction IDs, handle unsolicited events, disconnect, timeout and unsupported commands. Static extraction remains a hypothesis until controlled validation. | CELL-009 |
| SIM and registration | Map physical/logical slots, readiness and PIN policy, then network attachment and operator state. A displayed icon or ICCID is insufficient. | CELL-003 |
| Data | Negotiate contexts and APN policy, actual RX/UL PKTPROC/DMA, MTU, IPv4/IPv6, reconnect and cleanup; adapt native iOS packet interfaces. DIT is disabled in the captured configuration; Qualcomm IPA is not a substitute. | CELL-004/005 |
| SMS | Implement and measure message submission, delivery and receipt independently of data. | CELL-006 |
| IMS/voice | Verify IMS registration/signaling and real incoming/outgoing duplex audio. REINIT_VSS/ABOX coupling in the source is another dependency, not proof of a voice route. No live emergency calls are a test mechanism. | CELL-006, AUD-002 |
| Existing eSIM profile | Verified logical-channel/APDU and slot routing, then registration/data using an agreed test profile. Android eUICC feature inventory does not qualify this path. | ESIM-001/002 |
| Profile lifecycle | Selected OS frontend/ABI qualification, LPA/SM-DP+ and APDU session ownership, notifications, teardown/recovery, then controlled test-profile operations. Production profiles remain outside automatic tests. | ESIM-004, ESIM-003 |

Unknown firmware commands must remain unsupported. Do not manufacture successful readiness/registration replies to satisfy a UI. Do not replay inferred commands against the owner's running Android radio, share CPIF queues with Android, or start a native modem loop before recovery and device authorization.

## Donor validation

The [donor-model procedure](donor-model-check.md) produced an initial GCC compile failure under `-Werror=type-limits`. A separate explicit Clang 18 run built and executed all seven unmodified C model targets with ASan/UBSan and the same warning-error policy. [Fail](../../../state/evidence/QCOMMODEL-001.json) and [pass](../../../state/evidence/QCOMMODEL-002.json) are retained. This checks the selected donor models, including eSIM transport/cleanup/cache cases; it does not build the production IOKit bridge or establish iOS 16.5, Samsung hardware, network service or provisioning.

Resume with CELL-009 for offline command-schema work and KRN-001 for the blocked full-kernel build. CELL-002 must not fill missing live platform inputs from an older Samsung/Pixel table. The host framing model can be extended and fuzz-tested locally without a phone; exact platform addresses and firmware limits still need primary evidence.
