# DRV-005: GPT extent admission for the read-only UFS boundary

Evidence category: host-test. No phone, MMIO, controller or storage access happened, and no real
GPT was examined. Test tables are built in the test itself.

## What exists

`src/platform/storage/ufs/gpt.{h,c}` is a pure function over bytes the caller already holds. It
validates a primary GPT header and its entry array, then returns the extent of one named partition
in the form `struct ufs_policy` takes. The existing DRV-004 boundary then enforces that extent on
every READ(10).

## What it rejects

| Area | Rule |
| --- | --- |
| Header | Exact signature, revision 1.0, 92-byte size, zero reserved dword, zero tail of the block, valid CRC32 |
| LBAs | Header at LBA 1, backup header on the last block of this LUN, array after the header and wholly before the usable range, room for the backup array between the usable range and the backup header |
| Reservation | At least 16,384 bytes reserved for the array on each side, more if the array needs it |
| Array | 128-byte entries, 1 to 256 of them, buffer length exactly as declared, valid CRC32 |
| Entries | Unused entries entirely zero; used entries inside the usable range and non-overlapping |
| Lookup | Exact case-sensitive ASCII match; a name appearing twice is ambiguous and refused |
| Policy | A request for the name `userdata` is refused in any letter case |

The whole table is validated before any lookup, so a damaged entry fails a lookup of an unrelated
name. Each negative test recomputes both CRCs, so the rule under test rejects the table rather than
a checksum mismatch.

`userdata` is refused as policy. It is treated as encrypted, and reading it from XNU is not assumed
possible. Its encryption on this device has not been measured here. Refusal does not mean other partitions are safe or readable.
The refusal looks only at the requested name. A disk can label Android data with any other name, and this code cannot tell.

## What this does not establish

- That any real S24 GPT has this shape. Samsung's layout on this device has not been read, and
  the strict rules may refuse it. Refusal is the safe outcome, but it would need a measured reason
  before any rule is relaxed.
- That the geometry rules match the normative UEFI text word for word. See
  [hardening/handoff.md](hardening/handoff.md) for where they were checked.
- Anything about `UniquePartitionGUID`. It is not checked, because lookup never uses it.
- Anything about the protective MBR, which is not passed in.
- That the extent is applied to the right LUN. Nothing binds an extent to the LUN it came from.
- That the bytes came from the device: the caller must qualify its source. The buffers must also
  stay unchanged during the call, so they must be a kernel-owned copy rather than a DMA buffer the
  device can still write.
- The backup GPT is not examined, so a corrupt primary is reported rather than repaired.
- UFS PHY, IOMMU and MCQ compatibility. Nothing here touches hardware.

## How to check it

```sh
python3 src/platform/storage/ufs/gpt_check.py --run NAME
```

This builds the tests under ASan and UBSan, then applies single-line mutations and fails if any
mutant passes. Do not run it while a heavy lease is active.

See [ram-root.md](ram-root.md) for the initial root plan.
