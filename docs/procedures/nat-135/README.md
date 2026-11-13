# NAT-135: read-only SuperSpeed probe on the phone (pk1): USBDP PHY control block not readable at loader entry

Owner claude-opus-usb130-20261113. Evidence kind native-device. One run under decision 0054 (standing permission 0052), reboot
requested 2026-11-13T17:48:12.8Z. No PMIC/ACPM operation, no register write by the probe. **Outcome: inconclusive.** U4, U5 and U11
are answered, but the probe stopped at entry 35 under its pre-registered rule, so U7 (GPIO) was not reached.

## Established (artifacts/nat-135/run-001/delivery/peek.jsonl, values read by the loader on the phone)

- The RECOVERY readback matched 98f38989…8f69 before the reboot. The loader enumerated on host bus 7 (HS) at +18.5 s, and the
  companion was ready after 28.4 s.
- Entries 0-34 answered, and entry 35 (USBDP RST_CTRL `0x178d0000`) did not: the control transfer timed out after 5 s. The probe
  stopped there, journalled the error, and no delivery was attempted (`register probe stopped at PEEK 35`). The loader stopped
  serving USB (collector GET_INFO timeouts, `reason: unresponsive`).
- **The run still ended by itself.** The loader device disappeared at +490.7 s, which is the deadline instant: NAT-132 returned at +490.9 s.
  Download Mode followed 4 s later, without the owner's keys and without SEC_UPLOAD. A CPU stalled on an APB read therefore
  leaves through the same deadline path as a normal run. The mechanism is not identified (presumably the loader's hardware
  watchdog/deadline programming); only the observed timing is claimed.

| U | answer |
|---|---|
| U4 | DWC3 GSNPSID `0x33313130` ("3110", DWC_usb31), **VER_NUMBER `0x3139302a` = 1.90a**, VER_TYPE `0x6c703031`. 1.90a ≥ 1.20a, so NAT-131 S19's LLUCTL/FORCE_GEN1 branch applies |
| U5 | PMU `0x1286061c` = 1 (USB2 PHY isolation released by the USB2 ladder); **PMU `0x12860620` = 0: the USBDP combo PHY isolation is not released**. CMU_HSI0 gates `0x17802054..64` all `0x00200000` (CGVAL=1, MANUAL=0, AUTO=0: on under hardware control); QCH S_CTRL/EUSBCTL/LINK/SUBCTRL/TCA `0x2` (CLK_REQ=1, QCH_EN=0); DBG_NFO QCH S_TCA `0x4`. **With the clock gate on and the isolation set, a plain read of the USBDP control block (`0x178d0000`) does not complete**. TCA (`0x178e0000`) was not read |
| U6 | not reached: PHY_CONFIG0's power-stable bits are in the unreadable block |
| U7 | **not reached** (CMU_PERIC2 and GPC7 entries come after the USBDP group) |
| U11 | GUCTL `0x0a416802`, bit 21 NOEXTRDL = 0: not set, as NAT-131 inferred for Android |
| U8 | measured at the restore: Download Mode `8-1` **speed 5000, bcdUSB 3.20** (restore-001/download-mode-sysfs.txt). S-Boot's Download Mode runs SuperSpeed on this cable |

Other values at loader entry (not judged; reset defaults and S-Boot writes cannot be told apart from one sample):
- GUSB3PIPECTL0 `0x01001002`: bits 1, 12, 24; SUSPHY (17) = 0, DISRXDETINP3 (28) = 0.
- LLUCTL0 `0x008b8080`: PIPE_RESET, EN_US_HP_TIMER, PENDING_HP 0xb and LTSSM_TIMER_OVRRD set; **FORCE_GEN1 = 0**, TX_TS1_CNT = 0.
- LSKIPFREQ `0x4e928162`: [23:20] = 9, [26:24] = 6 (the vendor writes 5), bit 27 = 1. BU31RHBDBG `0x8` (bit 3, as the vendor sets).
- GUCTL1 `0x00001988`: vendor bits 21-24/31 clear.
- DCFG `0x008a0808` (HS, the engine's) and DSTS `0x00824388` (CONNECTSPD HS, link U0).
- USBCON LINKCTRL `0x0a553ff0` (bits 16 and 18 set, 17 clear = the loader's PIPE3 detach); LINK_CLKRST 0; HSP_MISC `0xc000`;
  LTSTATE_HIS `0x000ffff4`.

## Restore

Download Mode was bus 8 / address 5 at 2026-11-13T17:56:27Z. nat-012 restore_stock.py exited 0 (100663296 bytes acknowledged, session
end and reboot confirmed). check_android: SM-S921B/e1s/S921BXXS9BYH3, boot_completed=1, user-data directories present, full
RECOVERY hash 96620b8b…bf67. NAT-013 assess: pass. Native permission closed. These are minimal checks.

## Interpretation and next step

The read-only probe has reached the limit of what it can see. NAT-131's ordering (S3 releases the PIPE3/combo-PHY isolation at
PMU `+0x620` before any USBDP register access, S5 onwards) is now also the access precondition. The next experiment (NAT-136 host,
NAT-137 native) will:
1. read CMU_PERIC2 and GPC7 first (U7), before anything that can stall;
2. perform S3 alone: PMU `0x12860620` bit 0 := 1, with readback;
3. read TCA and USBDP;
4. restore bit 0 to its entry value.

A USBDP read that still stalls after S3 points at the rails (U6): Android shows vdd075/vdd12/vdd18/vdd33_usb on at
0.75/1.2/1.8/3.1 V (NAT-133), but which PMIC LDOs these are is not yet mapped. That mapping is host research before any power
operation. No SuperSpeed claim follows from this run.
