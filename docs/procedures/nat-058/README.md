# NAT-058: first native run of `loader-diag-xnu-ckpt3-usb` (decision 0024), 2026-11-11

Evidence kind: **native-device**. On 2026-11-11 the host computer received, by itself and without a camera, the text notes of the XNU kernel's own early
boot code on the S24 (SM-S921B/e1s): all 22 stops of the image's list, ending at C checkpoint 16, then the loader's `HOLD` record. This is the first time
the kernel's C code was observed past C checkpoint 11 (run 009 of NAT-022/NAT-034 ended there) and the first time the kernel's state at each stop reached the
host as a message rather than as a photograph.

## What ran

* Decision `docs/decisions/0024-nat052-loader-diag-xnu-ckpt3-usb-single-run-2026-11-11.md` (decision 0019 protocol); the owner's confirmation of the single run
  ("Да, один запуск loader-diag-xnu-ckpt3-usb (Recommended)") was recorded and committed (`fd5a57c`) before any device access.
* Image: RECOVERY SHA-256 `a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97` (NAT-052 `package-002`, `loader-diag-xnu-ckpt3-usb`; its
  `Image.payload` is `9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e`), written to `/dev/block/sda18` only, full readback equal;
  one `adb reboot recovery` at 2026-11-11T17:21:21.895Z (T0).
* Driver `docs/procedures/nat-057/session_nat052.py --image loader-diag-xnu-ckpt3-usb --out artifacts/nat-058/run-001 --execute`; analyser
  `docs/procedures/nat-057/analyze_nat052.py` (command lines in `evidence.json`). Before the run the preflight printed `ready-read-only`; the watcher
  (start record at T0 - 0.3 s) and the collector (first poll before T0, heartbeat file) were running before the reboot request.
* Registry steps in the same window, as decision 0024 and the owner's confirmation describe: `native` opened citing decision 0024, `task done NAT-043`
  (evidence fa32ec6), NAT-058 added and claimed, `task done NAT-058` while `native` was open, `native` closed.
* Restore: the phone re-enumerated by itself as 04e8:685d `SAMSUNG USB` (never `SEC_UPLOAD`) at T0 + 87.8 s; NAT-013 `restore_stock.py restore`
  (venv python, bus 5 address 93, one session) returned stock RECOVERY (`96620b8b...`); `check_android.py` read back the full-hash match, `boot_completed=1`,
  user 0 and the user-data directories; `assess` = pass with all six stages. No data, app or setting was touched.

## What the host observed

| T0 + | Event (source: `run-001-usb-events.jsonl`, frame receive times in the archive) |
|---|---|
| -0.3 s | watcher started; phone present as 04e8:6860 `SAMSUNG_Android` |
| +3.8 s | phone left the bus |
| +26.8 s | **1209:0001 appeared** (the monitor identity of the image); first frame (boot record) received at +26.9 s |
| +26.9 .. +44.5 s | loader text and stage records (`loader_main` .. `pre_jump`, RAM zeroing and copy: the engine is not polled between them, as in NAT-043) |
| **+44.5 s** | **first kernel stop note `CK n=1`** (assembly checkpoint 1) |
| +45 .. +54.3 s | notes `n=2 .. n=22`, one about every 0.4 s (the loader's 0.3 s service window per stop plus the host's polling) |
| **+54.3 s** | **`CK n=22`: C checkpoint 16, final-stop bit (`mask=0x203e`)** |
| +55.6 s | `HOLD stage=0x51 code=0x203e` |
| +84.0 s | 1209:0001 left the bus (the NAT-044 deadline reset, 60 s deadline) |
| +87.8 s | 04e8:685d `SAMSUNG USB` (Download Mode) |

## What the host received (`run-001-ck-log.txt`, raw `artifacts/nat-058/run-001/archive/`)

* One boot in the archive (boot-id tail `8fac5dc7eb04ab7c`, the image's FNV-1a-64), 172 frames, 170 records, `dev_seq` and frame sequence contiguous,
  0 drops, 0 faults, 0 stalls; the manifest says `complete-received-stream`, 46810 bytes, 0 errors; the end frame says `reason=disconnect`,
  `unread_bytes=0`.
* The banner `NAT047 loader-diag-xnu-ckpt3-usb deadline_s=60 fault=0`, both ladder summaries `err=0` (R: 5 operations, W: 69, one line per access), the
  eight stage records, then 22 notes `n=1..22` whose checkpoint values are exactly the list of the image (`1,2,3,4,5,11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16`),
  then `HOLD`.

| n | checkpoint | MMU (sctlr bit 0) | SP | kernel TTBR0 | notes |
|---|---|---|---|---|---|
| 1-2 | asm 1, 2 | off (`0x30d8099a`) | `0x800aa080` | 0 | loader's own SP; VBAR `0x80081000`, then `0x9e183c000` |
| 3-4 | asm 3, 4 | off | `0xfffffff008060000` | 0 | VBAR `0x9e183c000`, then the kernel's `0xfffffff007437000` |
| 5 | asm 5 | off (`0x3454599c`) | `0xfffffff008060000` | `0x9e15ae000` | the kernel has built its table and is about to enable the MMU |
| 6-22 | C 11, 30-35, 12, 40-44, 13-16 | **on** (`0x3454599d`) | `0xfffffff00805fef0` | `0x9e15ae000` | `mask=0x3e` until the last; the last has bit 13 (`0x203e`) |

* The kernel's `TTBR0_EL1` at checkpoint 5 was **measured** as `0x9e15ae000`. NAT-035 and NAT-036 used this value from the instruction-level model and noted that
  it had never been read on the phone; it sits next to the measured `TTBR1` `0x9e15af000`. The model value is confirmed.
* The MMU-on state (`sctlr=0x3454599d`, equal to the value measured in run 009 at C checkpoint 11) is the same at every later C stop; the resume stub restored
  the kernel's SP, registers, SCTLR and `TTBR0` at each return and the kernel carried on: 17 C stops (n=6..22) mean 16 resumes from one C stop to the next
  (plus four assembly resumes and the checkpoint-5 resume into C). Run 009 ended at the first C stop by design (no C resume existed); this is the first
  hardware observation of the NAT-035 resume sequence.
* No exception note (`esr= elr= far=`) and no exception frame arrived; the kernel did not stop by itself.

## What the verdict says

`analyze_nat052.py` (archive plus watcher log): **PASS**. The same `received.bin` first gave PARTIAL (one reason: `no manifest.json: the collector did not
finish`) when it was analysed at 17:24Z, because the collector and the watcher were still inside their own 360 s window; after both exited by themselves
at 17:27:21Z the analysis was re-run (PASS). Both analyses are in the artifact directory; the committed copy is the second.

A PASS here says that the host received a complete and orderly list of notes **as written by the image**: the kernel's early boot code, resumed 17 times by
the loader's stub, reached C checkpoint 16 with the state above. It does not say that the kernel's state is correct, only what it reported.

## What is not established

* Anything after C checkpoint 16: the kernel's `TTBR0` changes in `arm_vm_init` (NAT-035 section 2) and the stub refuses later stops. The next step toward a
  running kernel is a resume model for the new `TTBR0` or a different transport that does not need the loader's stub after `arm_vm_init`.
* Whether the kernel would have continued past checkpoint 16 on its own: the loader holds there by design.
* The cause of the 17 s no-poll window before `CK n=1` (RAM zeroing/copy) is the same as in NAT-043; a longer unpolled kernel interval was not exercised
  (the notes are 0.3 s apart).
* One run: no repeatability statement. The `timeouts: 140` in the collector summary are the unpolled gaps, no drop was counted.
* Display state was not observed; nothing here is a display or GPU result.
