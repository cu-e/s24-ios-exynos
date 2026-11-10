# STR-037 closure — the 1042-body native DEVELOPMENT E1S image (2026-11-10)

Evidence category: **host-test**. No new link was run, nothing was booted, and the phone was not used.

STR-037 was registered on 2026-11-06 for a Codex owner (`codex-e1s-native-link-20261106-sr37`) that never claimed it. The Codex root coordinator stopped. On 2026-11-10, STR-041 performed the same deliverable under another Claude session: it consumed the accepted STR-036 caller and ran the genuine native DEVELOPMENT driver link once. STR-037 is closed here as **satisfied by STR-041**, by `claude-takeover-20261110-6c8f` under decisions 0002 and 0003, after an independent check. The link was not repeated.

## Independent checks made here (a session that ran none of the builds)

| Check | Result |
|---|---|
| Recomputed SHA-256 of the object, depfile, source and recipe of all 1042 index-002 rows (4168 files). | 4168/4168 match, 0 mismatches. 1042 unique IDs: osfmk 319, bsd 508, iokit 102, libkern 77, security 23, pexpert 11, libsa 1, san 1. `index-crosscheck-001.json`. |
| Staged link inputs (`link-001/evidence.json`) against the index. | All 1042 IDs are staged. 1025 are identical to the index. 15 differ because they are setsegname post-images (16 transforms: 14 `__HIB` objects, plus libsa `bootstrap.cpo` in two KLD passes); their raw copies keep the index hash. The other 2 are the STR-035 final overrides `osfmk/start.o` and `bsd/e1s_log.o`, whose staged hashes are the ones in `fixtures/public/e1s-kernel-log-objects/object-overrides.json`. |
| Component filelists. | Eight lists (osfmk, bsd, libkern, iokit, pexpert, libsa, security, san), 1042 entries in total. |
| Image. | `verify_image.py`, rerun into a new directory, returns pass: SHA-256 `4c9536d8…595f`, 21 539 800 bytes, ARM64 MH_EXECUTE, entry `__start` at `0xfffffff00743b4a8`, 0 undefined symbols, 0 dylib load commands, and the independent parser agrees with the executor. `verify-001.json`. |

## Obligations reported, not closed

- **check_all_exports.** Not run on this image, because the native DEVELOPMENT driver has no export-list flag. KRN-041 found that the genuine lists miss exactly 37 names. With `0001` (two arm64 pmap query definitions) and the opt-in E1S profile `0002` (removing 35 undeclared names), a relinked **test copy** passes both check_all_exports passes and all seven symbol sets. KRN-042 reproduced this from main. The patches are not yet part of any build tool, so this image itself is not export-checked.
- **private37 / full ABI.** These are the same 37 names. Contents of Apple's closed per-machine libraries were not inspected.
- **Archive closure.** Three archives were consumed (firehose, pthread, cc_kext). The link recorded driver diagnostics, not a blanket private ABI claim.
- **Physical mapping.** UNQUALIFIED. No packaging, loader payload, QEMU, boot or phone claim.

## Procedural deviation

STR-037's text reserves claiming and closure for the original Codex owner, with root routing. That routing no longer runs. The owner's decisions 0002 and 0003 allow a new owner to take unfinished work from stopped executors. This closure is a review of STR-041's work, not a second link, and STR-041's own limitations still apply. Its input review was by a same-session subagent and read index 001; the checks above cover index 002 fully.
