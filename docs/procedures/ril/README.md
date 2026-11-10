# CELL-009 — static command schema of the BYH3 Samsung vendor RIL (2026-11-10)

Evidence category: **host-test**, static inference only. Nothing was sent to the modem or phone. The library was not loaded or executed. Owner: `claude-takeover-20261110-6c8f`; the task was transferred from the stopped `codex-ril-inputs-20261105-m` under decision 0003.

## Input and analyzer

- **Input.** The CELL-011 read-only copies: `libsec-ril.so`, 5 459 848 B, SHA-256 `fa4c0b63…04ae`; `libsecril-client.so`, 134 368 B, SHA-256 `458cb6be…8adfb`. Both are from SM-S921B/e1s/S921BXXS9BYH3 and are kept local only.
- **Analyzer.** `tools/research/ril/schema.py`, using `llvm-nm`, `llvm-cxxfilt`, `llvm-objdump` and `llvm-readelf` from the pinned NDK 28.2.13676358. The script checks the input hashes and sizes before reading.
- **Command.** `python3 -I tools/research/ril/schema.py --run byh3-003 --publish` (exit 0). It writes `fixtures/public/ril/schema-byh3.json`, which contains names, C++ parameter types and header constants only. No code and no binary are included.

## Results

**Transport (kept separate from the command schemas).**
- Device nodes: `/dev/umts_ipc0`, `/dev/umts_ipc1`, `/dev/umts_rfs0`, `/dev/umts_boot0`, `/dev/nr_rfs0`, `/dev/nr_boot0`.
- I/O classes: `IoChannel` and its variants (serial, socket/phonet/MHI/unix, ioctl, HAL, VM).
- Entry points: `IpcModem::SendMessage`, `SendMessageSync`, `ReceiveMessage` and `SendRawIpc`.
- **Frame header, 7 bytes.** It was read from `IpcProtocol::MakeHeader`, which loads u16 @0 and u8 @2, @3, @4, @5, @6. Its format string is `%s %3s (M)%s (S)%s (T)%s l:%x m:%02x a:%02x [ `. Fields: length u16, main sequence, ack sequence, main command, sub command, type.

**Protocol 4.1 inventory.**
- 34 `IpcProtocol41<Group>` classes.
- 588 request builders (`IpcTx*`), with full parameter types taken from the mangled names.
- 424 response/notification parsers (`IpcRx*`). Nearly all take the raw `(char*, int, int&, RegistrantType&)` payload, so their names are known but their field layouts are not.

**Header constants of the requests.**
- The analyzer matched each IpcTx function's `mov` immediates stored with `strh` at base+4 and `strb` at base+6.
- Results: 312 recovered, 9 ambiguous, 267 unknown. The unknown ones build the header indirectly, for example through a packet builder or a computed value.
- Control: `Sim.GetAtr` comes out as main 0x05, sub 0x0a, type 2, which matches its disassembly by hand.
- The recovered main commands are consistent within each group: Sim 0x05 (14), Net 0x08 (46), Sms 0x04 (13), Pb 0x06 (3), Stk 0x0e (5), Sap 0x12 (8), Data mostly 0x0d (18).
- The type byte takes only the values 1–5.
- Data also shows 0x17 (5), 0x03 (4) and 0xff (1). These may be other groups' messages or heuristic mistakes, and they are flagged as uncertain.

| Domain | Groups | Requests | Recovered IDs | Parsers |
|---|---|---:|---:|---:|
| SIM / APDU | Sim, Sap, Pb, Stk | 50 | 30 | 47 |
| Registration | Net, JsonNet, IilNet | 89 | 47 | 66 |
| PDP | Data, JsonData, IilData | 71 | 30 | 54 |
| SMS | Sms, IilSms, Mms | 25 | 15 | 16 |
| IMS | Ims, Qmiims, IilIil | 14 | 5 | 9 |

The APDU-related subset, 34 entries (Transmit/Exchange/Channel/PCSC/ATR/SAP/UICC auth), is listed separately under `domains.sim.apdu_related`.

## Unknown, kept as unknown

- Header constants for the 276 requests marked unknown or ambiguous.
- Header constants for every parser: the receive dispatch was not traced.
- Payload field layouts and lengths.
- Which commands the BYH3 modem firmware accepts.
- Any hardware behaviour.

Unknown commands stay unsupported and are never sent to the daily phone. No replay, fuzzing, modem reset or profile operation was done.
