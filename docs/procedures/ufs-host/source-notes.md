# Pinned source findings for DRV-004 and DRV-002

These are source facts and host qualifications, not observed controller state.
The Samsung source pin is417484173abc2c4fa93e738ea82ad9f2e84911b1; the E1S pin
is c8860decc62c6d6180e609036d027a2997972420. Exact hashes, blob identities and
URLs are in `src/platform/storage/ufs/source-profile.json` and actual evidence.
RES-002 used a separate BSP pin f85e53cfa5497ead5d78821efbac84e51f37a4e1.
Neither pin is established as the exact running S921BXXS9BYH3 firmware source.

| Primary input | Qualified interpretation |
| --- | --- |
| Samsung `include/ufs/ufshci.h` | Genuine UTRD 32/CQE 32/PRDT 16-byte declarations, lower 16-bit length then upper 16-bit DWORD offset, 512-byte UPIU slots, D2H/interrupt/native-storage constants |
| Samsung `include/uapi/scsi/scsi_bsg_ufs.h` and `include/ufs/ufs.h` | Genuine 12-byte UPIU header and 40-byte command response body, big-endian residual and sense-length fields, response 0x21 and read/write flags |
| Samsung `drivers/ufs/core/ufs-mcq.c` | Actual `ufshcd_mcq_get_tag` masks address bits 63:7; bits 4:0 encode SQ ID, bits 6:5 reserved; UCD array stride must satisfy allocation/alignment rules |
| E1S `0005-e1s-ufs.patch` | Actual pure command builder agrees byte-for-byte with owned READ(10) profile on 56 cases; command and response slots 512 bytes, up to four 256 KiB PRDT entries |
| Samsung `s5e9945-ufs.dtsi` | HCI 0x17100000/0x3000, MCQ 0x17100400/0x600, SQD 0x17140000/0x15100; source has DMA-coherent property and power/IOMMU context, not a measured handoff |

The independent oracle compiles original declarations, not a handwritten
replacement header. Actual donor builder and Samsung tag function bodies are
extracted unchanged; explicit host adapters supply primitive endian types,
stand-in context, MIN/bzero, division and compile-time assertions. No MMIO
function or native init/reset sequence is included. Vendor copyrights and
license notices remain in complete primary inputs and generated oracle header.

Useful boundaries for the future kernel task:

- The donor completion path checks OCS and response bytes 0/6/7, but the reviewed
  function does not validate current CQE address/SQ ID, UPIU LUN/task tag,
  residual/sense or underflow/overflow before reporting success. Owned admission
  adds these checks and rejects unsupported response variants.
- The donor retry helper retries all command errors up to three times; its
  timeout path alone does not establish actual DMA quiescence. Owned state
  quarantines on timeout/matching error and exposes no automatic retry/reset.
- The donor uses one UCD at DMA offset 0x1000. Its 1088-byte structure is not a
  128-aligned pool stride. Actual Samsung tag recovery requires the actual
  padded UCD allocation stride; never substitute `sizeof(owned packet)`.
- Donor READ CAPACITY(10) handling does not qualify the 0xffffffff sentinel as
  READ CAPACITY(16), and uses 32-bit `last+1` in reporting. Host policy therefore
  takes independently qualified capacity instead of trusting that helper.
- Donor GPT lookup checks signature, bounded entry count/size and `last>=first`,
  but the reviewed function does not check header/table CRCs or all LUN/extent
  ranges. This task does not add a GPT parser or authorize partition access;
  host admission requires already-qualified capacity and extent metadata.
- Software epoch/generation is absent from physical CQE wire bytes. Never
  reset a logical epoch and reuse UCD/task tags while old completions or DMA
  can remain. Hardware cleanup/queue drain/coherency proof is a separate gate.

No native PHY/IOMMU/cache operation, address ownership, firmware compatibility,
bootability, encrypted userdata read or safe Android return follows from these
source findings. A RAM root avoids depending on unqualified storage for early
kernel bring-up; it does not itself authorize a native boot.
