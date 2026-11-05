# KRN-032 handoff

Owner: codex-team-crypto-des-20261105-bs. Worktree: worktrees/krn-032-20261105. In progress, not accepted.

Source/API milestone: exact selected callback/helper declarations and caller key/storage policies mapped; genuine Apache-2.0 Mbed TLS DES primitive and dependency headers staged with full pin/license/file provenance. Eight typed ECB/CBC callback variants and bounded self-contained schedule bridge implemented; no shared runtime/XTS/global zeroizer edits. Roundkey is NULL with no selected caller demand, helper policy is 8 bytes only, 16-byte TDES is a separately labeled local extension.

Memory gate initially prevented new test processes (MemAvailable 789320 KiB); source preparation continued. Coordinator now reports recovered memory and authorizes bounded per-run-guarded host/ARM checks, no QEMU lease yet. DES001 registered before algorithm execution.

Next: generate primary NIST and independent OpenSSL corpus, implement contract tests and bounded checker, run host sanitizer and typed ARM checks, then request exclusive QEMU lease. No algorithm/CPU pass is yet claimed. No phone/provider/private ABI/FIPS/side-channel/kernel claim.

Host/ARM milestone: `artifacts/crypto-des/host-arm4/evidence.json` passes 2936 vector executions (1000 untouched ordinary NIST records, 1900 repeated-key DES / local EDE2 reductions, 36 deterministic independent OpenSSL extras), 164050 sanitized host checks, five profile rejection controls and two executed sanitizer detectors. Genuine selected helper typedef assignments and schedule declarations compile on ARM64: 144/400-byte states fit 256/768-byte slots; descriptor sizes 48/40. Two synthetic Mach-O images link using the unchanged accepted XTS zeroizer/AES/memory artifacts. This is not CPU execution yet. Initial parsing/compiler attempts host-arm1..3 remain retained, no successful claim from them.

A few additional misalignment/wrap preservation checks and explicit native zeroizer/import audit are prepared for the frozen final qualification. Coordinator granted one exclusive 256MiB QEMU guest, with 512MiB total owned RSS to include emulator/supervisor overhead; host/compiler cap remains256MiB, MemAvailable floor4GiB. No other guest may run concurrently. Planned positive/corrupt-vector/wrong-cookie/spin controls remain pending at this checkpoint.
