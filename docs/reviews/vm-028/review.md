# REV-032 console preflight review

No actionable P0/P1/P2 finding was identified within VM-028's source-preflight and untrusted-console diagnostic scope through `cebbe14968b37f407b63caa689bbace3c515e341`. The selected implementation is `e95909294487b4ad7f05a13804fdf5da1066dc51`; `c1520be29c12a3364a7d512cab390d4ce6fd4ef4` isolates the missing DEVELOPMENT-flag control. Tool SHA256 is `43f42e99d205e645bb58f85e60eb68d91a2238b5333275f488f1abecf1e5812c`, fixture SHA256 `5ceaaf24afe4bcce614584c907a67c0e1685f3dd823cdf130f52e8dfe3c9dc5e`. Source acceptance does not establish a genuine runtime console.

Reviewer `codex-review-boot-gates-20261106-ee`; branch/worktree `team/rev-boot-ee-20261106` / `worktrees/rev-boot-ee-20261106`, based on MAIN `12a43ee`. Only `docs/reviews/vm-028` is committed. Original producer files and prior evidence remain unchanged. VM-010 remains under its separate original owner, and existing completed/blocked claims are unchanged.

## Source route and exact provenance

The review independently rehashes all 12 source files and checks all 37 recorded line facts against their actual text. Five console-related objects match the source paths/hashes in frozen graph `afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`: startup, ARM initialization, platform initialization, kprintf and serial. This is source/object-selection correspondence, not proof that those exact objects were compiled, linked or executed.

QEMU commit `698104725efad4b29079d857dfdebbd804e34c99` maps virtual UART0 at `0x09000000`, declares PL011 compatibility and connects serial output. Scion commit `a6f4bc38aa244359cd365c976244a88c9d6b3304` discovers that FDT device and emits Apple-DT `/arm-io/uart0` with a relative register range and boot-console property. The actual recorded VM-005 shim source hashes agree with the prepared Scion `avfboot.c` and `uart.c` bytes used by this route; its QEMU pin agrees with the primary qualified source descriptor. No shim or QEMU binary was launched again.

The selected BCM2837 header enables `VMAPPLE_UART`. Actual XNU source chooses the PL011 branch unless the device is explicitly `ns16550a`, maps the virtual range with `ml_io_map`, polls FR offset `0x18` bit `0x20` and writes a 32-bit DR at `0x00`. Those are source observations for the selected virtual board; they are not physical S24 MMIO operations or compatibility evidence.

The source trace supports the diagnostic proposal: `debug=0x8` supplies DB_KPRT; DEVELOPMENT additionally checks the presence of `-enable_kprintf_spam`; serial output/input bits are `0x1`/`0x2`, while on-demand is `0x40`. The selected ARM initialization prints its early kprintf/serial markers and switches to serial only when output is selected and a device exists. The shim otherwise defaults to `console_quiet=1`; the proposal explicitly requests `console_quiet=0` and the source-supported polling option.

The argument checker validates a proposed string. It does not parse a payload or reconstruct the shim's final combination of default, payload and FDT arguments. The shim itself prepends a debug argument, so its final line need not equal the proposal token-for-token. Before runtime interpretation, the integrator must bind and inspect the actual payload command line, FDT append and printed final combined arguments. The source preflight grants neither compilation nor QEMU authorization.

## Actual recorded bytes and independent controls

The real input is VM-005's `run-final-221923b/positive.log`, SHA256 `e861383dcb4ae1f27df0111758ccc0aa8855937398e680bad30498c663d951ba`. Its original report binds that exact console to an owned synthetic payload, reports exit0, and explicitly records XNU/PID1 execution as false. The console's shim handoff and `VM005 SYNTHETIC PASS` are not genuine XNU output. The reviewed diagnostic classifies those actual bytes as `rejected-synthetic-input`, and a fresh actual CLI invocation exits2.

The independent review passes 218 checks, including 43 owned diagnostic mutations and four finite CLI controls. All authored bytes are retained as test inputs, never reported as new guest measurements. Cases include:

- Actual synthetic trace plus a spoofed Darwin banner, which remains rejected.
- Removal of all recognized synthetic tags, followed by injected kernel-like stages. The classification becomes explicitly unverified; genuine-kernel/PID1/natural-Stop fields remain false.
- Truncated actual-log prefixes and banner prefixes, compiler-prefixed markers, selected-version substitution, CRLF and invalid UTF-8 bytes. Raw digest and classified-byte count match the exact input bytes.
- Fatal/panic precedence despite later banners, reversed first-stage order, complete counts with retained line-index arrays capped at32, the exact64 KiB line boundary and rejected line/total-size overflow.
- Source/path/fact/parent-manifest/object-source substitutions, isolated DEVELOPMENT-flag omission, conflicting/silent/on-demand argument proposals and exclusive output creation.

The four actual CLI exits are2 for the recorded synthetic trace,0 for an authored unverified banner sequence,1 for isolated missing DEVELOPMENT flag, and1 for a pre-existing output path. The existing output sentinel is unchanged. Exit0 means classification completed; the fresh output still has `genuine_kernel_success=false`. Every accepted diagnostic retains false genuine-kernel, PID1, natural-Stop and native-phone fields.

The independent process wrapper samples owned RSS, enforces a finite15-second CLI deadline and confirms no live owned child after each command. Stable three-sample admission remained >=4 GiB. Current controller VmHWM peaked at119,296,000 bytes, sampled combined controller/child RSS at134,524,928 bytes, below256 MiB. Historical inherited ru_maxrss is recorded separately. No compiler, preprocessor, linker, QEMU, common check, producer edit or device operation occurred.

## Limits and next gate

The order flag describes the first recognized occurrence of each marker. An otherwise ordered authored transcript followed by another early shim marker still reports first-observation consistency. This diagnostic is not a complete single-boot protocol or reset/replay validator. The observed behavior is retained explicitly; it does not promote runtime success because all such fields remain false. Log handling was assessed on regular immutable recorded files and owned finite parser/CLI inputs; no general live-stream monitor or operating-system authenticity is claimed.

The producer's original eleven controls and their artifact hashes were inspected, including its follow-up isolated flag check. Original source-binding needle and exploratory-path errors remain in producer evidence. This review's read-only exploration initially requested a nonexistent VM-005 `evidence.json`; the actual immutable capsule is `report.json`. That lookup error is not a product or compilation failure, and no producer file was changed to hide it.

Review evidence and exact scripts/source snapshots/raw controls are under `worktrees/rev-boot-ee-20261106/artifacts/rev-console/session1`; `assessment.json` binds the final capsule and report. Recommend acceptance only of this bounded source/parser result after integrator/root review and fresh common MAIN checks. Genuine console acceptance still requires reviewed source/object/link/image lineage, an admitted invocation bound to its actual payload and final arguments, raw console and independent execution assessment. Kernel runtime, PID1, natural Stop, full SDK/private ABI and native-phone capability remain unmeasured. Keep REV-032 in progress until the original reviewer is approved to close it; do not close VM-028 or change its owner's task.
