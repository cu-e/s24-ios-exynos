# NAT-117: image `loader-diag-xnu-sc5-md1` (D22AP /product in the ADT, wait dump off)

Evidence kind: **host-test**. Nothing here ran on the phone. Owner: `claude-opus-nat116-20261113`.

Cause addressed (from NAT-116, native): SpringBoard aborts in `-[_UIScreenComplexBoundingPathUtilities _loadBitmapForScreen:type:]`
because the asset catalog returns no `BoundingPathBitmap-1125x2436-375x812-3.00x`. The asset exists in
`UIKitCore.framework/BoundingPathData.bundle/Assets.car`. The project ADT has no `/product` node, which is where MobileGestalt reads
the artwork traits. That this is the cause is a **hypothesis**; NAT-118 tests it.

* `make_adt117.py`: NAT-085's ADT + the real D22AP `/product` (decoded from the pinned `DeviceTree.d22ap.im4p` of the local 20F66
  IPSW with `tools/ios/lzfse_py.py`), built by mkadt.py's `d22ap_product` rule: unflagged properties, no name/phandle, gamut sRGB,
  fresh phandle 17; 61 properties, +2,688 B. Output `44bbd1d0...`.
* `build.py`: wrapper over NAT-115's build that swaps the NAT-085 derivation in the running chain's instance (counted: derivation
  ran once, NAT-085's record names our hash, one ADT swap) and drops `wait_dump=1`. Kernel unchanged (`cc952151...`).
* Payload diff vs NAT-115 (byte compare): loader Image 13 bytes (payload hash/size immediates, capstone), inner header `adt_size`,
  command line, ADT, trailing bytes. Nothing else.
* `analyze118.py`: pass rule fixed before the run; NAT-116 → `A1-same-abort`, NAT-113 → `S1-alive-no-frame` (controls).
* `session_nat117.py` = `session_nat115.py` + 9 counted substitutions (`derive117.py --check`); without a decision file it stops with
  `device_write_started=false`, no commands.
* Tests: `test_nat117.py` 15 OK; `mutate_nat117.py` 14/14 killed.

Image: RECOVERY `9696818ff9ccc3f38276a7196a8a934085da8860758e8ef25788a0bc581b0536`, payload
`81b33e6de389b122e0e252d64d0cb221c3f6c5d3c4270a88472cc2cb298fd5c7` (26,141,200 B). Decision for the run: 0046.
