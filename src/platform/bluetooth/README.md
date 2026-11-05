# E1S Bluetooth preparation

BT-001 provides independently authored freestanding C **host models**, with no UART, GPIO, firmware, file, network or clock I/O. [profile.json](profile.json) separates pinned board facts, a derived historical Android IRQ association, and unknown live inputs. The [source review](../../../research/notes/RES-006-bluetooth-donors.md) explains firmware and iOS donor limits. This code does not implement native Bluetooth.

```sh
python3 -m unittest discover -s tests -p test_bluetooth_transport.py -v
python3 src/platform/bluetooth/check.py --run unique-bt-run
```

Register explicit experiments first as described in [BT-001 procedure](../../../docs/procedures/bt-001/README.md). Build inputs, command logs, hashes and object headers are preserved under ignored artifacts/bluetooth-transport/. No upstream programs run. Existing run names are rejected.

## Byte-stream contract

The caller allocates state and a workspace of 5 through 65,540 bytes, selects RX/TX direction, explicitly enables optional QCA IBS, and supplies monotonic milliseconds. H4 command/ACL/SCO/event/ISO framing uses bytewise length reads; ISO length uses its low 14 bits. This establishes framing only, not ISO/LE Audio controller support or higher-level HCI validity. IBS FC/FD/FE are recognized only at a packet boundary when enabled; payload bytes remain opaque. There is no IBS wake/retransmit/power state machine.

Each feed processes at most 4,096 bytes and 64 frames, returning exact consumption for continuation. Fragmented headers/bodies remain in the workspace. Invalid type/direction, excessive declared size, frame deadline, clock rollback or consumer error quarantine the stream. No guessed resynchronization or automatic callback replay occurs.

Callbacks synchronously borrow a complete frame including indicator; they cannot retain its pointer, mutate/reinitialize state, or call concurrently. Same-parser feed recursion returns BUSY. All C state/input/workspace/output storage must be valid, stable and nonaliasing; this is not a userspace pointer validator. The adapter must bound callback execution; byte/frame budgets cannot preempt a blocked callback. Deadlines are caller-polled policy limits, not a hardware watchdog.

## Exclusive initialization commands

The command model tracks one pending opcode on an **exclusive initialization channel**, not arbitrary asynchronous Bluetooth procedures or multiple daemon clients. Initial credits must be an explicit input. Begin consumes one credit; Command Complete/Status update the controller-advertised credit count, including opcode-zero credit notifications. Unrelated opcodes cannot complete the pending command.

Command Complete returns raw parameters without inventing a universal status layout or success. Command Status zero means accepted and leaves the command pending; nonzero is preserved as rejection. Use this model for commands whose terminal outcome is Command Complete. Connection procedures and vendor EDL event formats need separate verified state machines.

Timeout/clock rollback quarantine the session and retain pending ownership. Late responses and same-opcode retries remain rejected after timeout. Stop prevents new work and retains pending work; a later matching completion can clear logical pending state without resuming submissions. No code frees DMA, resets a controller, proves UART drain or changes power. Epoch is local bookkeeping absent from H4 wire replies; reinitializing it cannot distinguish an old response. A native adapter must prove physical session isolation before reuse.

## Actual validation and next work

BTMODEL-001 passed 20,000 deterministic mutation/control attempts under host ASan/UBSan, with 4,858 quarantined streams and 15,581 synthetic frame callbacks. Seven unit-test groups exercise fragmentation, opaque IBS bytes, direction, bounds, budgets, deadlines, recursion, credits, raw errors, Stop and late replies. Four compile-only objects cover core C and C++ layout for AArch64 ELF and arm64 iOS16.5 Mach-O. No Apple SDK, XNU linkage, ARM execution or hardware support is established. [Public report](../../../fixtures/public/bluetooth-research/bt-model-session1.json) retains exact commands and hashes.

BT-003 must implement actual Exynos UART/CMU/pins/IRQ or DMA, shared power/wake and versioned firmware initialization against pinned XNU. BT-004 must implement the selected iOS16.5 transport/control/BlueTool and truthful vendor adaptation. BT-002 and BT-005 are separately gated native pairing/BLE and audio/coexistence qualification. Native capabilities remain not-tested.
