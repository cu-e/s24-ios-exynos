# NAT-188: Reduce Transparency and Reduce Motion on the phone (native, decision 0076)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scW-md1 (NAT-187), one run on 2026-11-14. Afterwards stock RECOVERY was
restored with a full hash check (`restore-001/report.json`, nat-013 assess: Android booted, RECOVERY readback matches) and Android was
verified.

## Result: B0, the render server costs the same

| | NAT-186 (scV) | NAT-188 (scW: + Reduce Transparency, Reduce Motion) |
|---|---|---|
| backboardd CPU per frame, median of the swipe spans | 67.95 ms | **67.27 ms** (p25 48.4) |
| backboardd share of cpu0 | 0.768 | 0.734 |
| cpu0 busy (top186) | 0.996 (U-sat) | 0.99 (U-sat) |
| 60-Hz share of frame intervals, 218–378 s | 0.594 | 0.513 |
| expensive phase (≥ 130 ms per frame) | 315–375 s | 315–350 s and 370 s |
| driver time (K) | 2.162 ms | 2.011 ms (K2) |

The other verdicts are unchanged: swipe175 F60 by the registered rule (the same caveat as NAT-186), dpp177 R-ok, cpuclk173 C2, touch170
P1 and display W-ok / D2. The timed return was reached, 54 swipes ran and the sampler finished.

### Did the setting take effect?

The log has no line naming the preference. In the last panel frame, a home page, the pill above the dock is solid dark (thumbnail
brightness 21) and the dock is darker (mean 82, against 164 in NAT-184's last frame). That is how Reduce Transparency draws them.
However, the two frames show different pages, so this suggests the setting took effect but does not prove it.

### What it means

Either way, removing the blur and motion effects did not reduce backboardd's CPU per frame. On this phone, the cost of software
composition is not the blur materials. It is the composition itself: about 2.7 million pixels per frame at 1125×2436, through
CoreAnimation's CPU renderer on one A520 at 1958 MHz.

The levers that remain are not software settings:
- **More and faster cores** for backboardd's render threads. The SMP line, NAT-154, is stopped by the classifier and awaits the owner.
- **GPU composition on the Xclipse 940.** It needs SMC/HVC and PMU steps that await the owner's decision.

## Not established

- Proof that the preference was read: no log line, and the frame comparison is suggestive only.
- What exactly makes backboardd's frames cost 30–250 ms.
