# NAT-187: scW, Reduce Transparency and Reduce Motion in the delivered root (host)

## Why

NAT-186 measured cpu0 full during the swipes, with backboardd, the CoreAnimation render server, taking 76 % of it:
- **CPU per frame:** about 30 ms on home-page swipes and about 190 ms in the Today view. On this analyser's spans the median is
  67.95 ms per frame.
- **No GPU:** without one, every blur material (dock, folders, widgets, the Today view) is computed on the A520.

iOS's own settings remove those effects:
- **Reduce Transparency** turns materials into plain colours;
- **Reduce Motion** turns zooms and parallax into fades.

Both are preferences in the userland root. Changing them involves no hardware.

## What changed (the small root only)

`build_ax_root.py` derives `artifacts/nat-187/pid1-sc2-hb-ax/root.apfs` (SHA-256
`3f91915709307fe2826ecbb1dee86c01b875e91ea060796c645051ee8a32cd49`, 4 MiB, 397 files) from NAT-110's `pid1-sc2-hb` (396 files) with two
changes:
- **Added:** `var/mobile/Library/Preferences/com.apple.Accessibility.plist` (0644), a binary plist with exactly
  `EnhancedBackgroundContrastEnabled = true` (Reduce Transparency) and `ReduceMotionEnabled = true` (Reduce Motion).
  - The domain and both keys are strings of the donor libAccessibility in the iOS 16.5 dyld shared cache (`dyld_shared_cache_arm64.05`,
    next to `EnhancedTextLegibilityEnabled` and `DifferentiateWithoutColor`).
- **Changed:** `etc/var.skel` gains one line installing it as `/private/var/mobile/Library/Preferences/com.apple.Accessibility.plist`
  (0644, 501:501), the same form as NAT-108's eight preference lines.

The root went through `mkapfs.py`, `verify.py content --all` and the kernel `apfs_lib` readback: 397 of 397 files, no mismatch.

**Image** `loader-diag-xnu-scW-md1` (`build.py`):
- **Kernel:** NAT-185's (`d7e7fee1…`), unchanged.
- **Command line:** NAT-185's with the tag `nat_attempt=NAT187-scW`, 254 B.
- **Pin.** The chain's pinned small-root hash (nat-113's `MD0_SHA256`) is replaced, only during this build, by the new root's verified
  hash. The build record shows the new root in every field: payload ramdisk, nat115, nat083.
- **Gates:** loader sites rc 0 / ok / bad 0; relocscan clean.
- **Package:** `artifacts/nat-187/package-001`, RECOVERY `fb65027cd6ddb7813b971d1918964027a5aa2c5a79fef4282859a83bad4f060c`.
- **Session:** `session_nat188.py` (88e8b06d…), derived by counted replacement from NAT-177's (`derive188.py --check`).

## Host checks

`python3 -B docs/procedures/nat-187/test_nat187.py`: 4 OK.
- **Root difference.** Against NAT-110 the root differs by exactly the plist and the one `var.skel` line. The plist decodes to the two
  booleans and has mode 0644.
- **Build records.** The image build used that root's hash and NAT-185's kernel.
- **Keys.** The domain and keys are NUL-delimited strings in the donor cache.
- **Analyser** `bbd188.py`. The boundary verdicts were tested. It reproduces the registered baseline (67.95) on NAT-186's log.

## Registered verdicts for NAT-188 (`bbd188.py`)

The verdict is the median of backboardd's CPU per frame over the swipe spans (220–375 s): its `e1s-top` time divided by the frames
the driver counted in the same span. The baseline is NAT-186's **67.95 ms**.

| verdict | condition |
|---|---|
| B-none | no span with frames (inconclusive) |
| B2 | ≤ 0.5 × baseline (≤ 33.98 ms) |
| B1 | ≤ 0.8 × baseline (≤ 54.36 ms) |
| B0 | otherwise: no clear gain |

Reported beside it:
- backboardd's share and the 60-Hz share of the driver's frame intervals (NAT-186: 0.594);
- top186, fbcopy181 (K), swipe175, dpp177, cpuclk173, touch170 and the display verdicts;
- the last panel frame, which should show plain dock and widget backgrounds if the setting took effect.

## Not established here

- Whether this iOS build reads the preference from that file at the point backboardd starts. If it does not, NAT-188 gives B0 with
  unchanged materials in the last frame.
- Which effects remain expensive.
