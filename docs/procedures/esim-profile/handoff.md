# ESIM-004 handoff

2026-11-05; owner `codex-esim-frontend-20261105-l`, main checkout. This goal turn made progress through a new pinned primary source, reproduced source defects, two retained patches and actual before/after offline results. Selected-image acceptance remains incomplete, with the precise external input gap below. No phone, subscription, profile, modem, firmware, Apple binary or native experiment occurred.

## What changed

- Added ARIstoteles `25cb9bb5c35993ed0c74248b96f0065d5479f447` to the source catalog; source-only sparse checkout excludes capture/crash binaries, watcher/injection/replay execution and installers. Main/nested libari licenses are MIT, copyright Tobias Kröll2021.
- Reviewed Intel ARI/CommCenter and libARI structure extraction as another frontend investigation path. The source README says18.3.1; CHANGELOG also describes unreleased27.0/24A435/Ghidra12.1.4 work. Neither qualifies selected16.5. No Ghidra extraction or supplied-image ABI analysis was run.
- Added a real offline donor checker under tools/research/esim-profile, independent invented wire bytes and two small patches under patches/cellular/ari. Original references remain unchanged; each experiment snapshots its checker and donor bytes in ignored artifacts.
- Updated the implementation contract with the actual unresolved frontend selection and kept Samsung vendor command recovery separate from ARI/QMI, raw IP and audio. No native capability status changed.
- Reviewed current official Apple API documentation: carrier-app/public-cellular-plan entitlement requirements do not supply a system LPA/private ABI. The local public-doc snapshot has recorded URL/status/hash; no Apple binary was acquired. Later eSIM-capable reference identity changes also require actual arm64e/PAC/loader qualification.
- Recorded fresh Reddit query limits separately. Combined results were unrelated consumer discussions; title/snippet screening is not body/code review or an exhaustive absence result. Prior archive coverage counts remain unchanged.

## Commands and results

Source acquisition: `python3 tools/sources.py fetch aristoteles`, exit0. An initial `git sparse-checkout add --no-cone ...` option was unsupported (exit1); retry without that unsupported option succeeded. The named __init__.py contains only the package comment. `python3 tools/sources.py verify aristoteles` exited0 after the explicit named-file expansion. No installer or upstream hook ran.

| Experiment | Actual command suffix to python3 tools/research/esim-profile/check_ari.py | Exit | Result |
|---|---|---:|---|
| ESIMARI-001 | --run ari-original-session1 | 1 | Unmodified donor:30 failures/8 errors; both original empty smoke tests pass |
| ESIMARI-002 | --run ari-patched-session1 --apply-patch | 1 | 0001 fixes independent wire/bounds cases; six actual bytearray pack-to-parse cases fail |
| ESIMARI-003 | --run ari-patched-session2 --apply-patch | 0 | 0001 then0002: seven groups pass, including mutable-buffer ownership and both upstream smoke tests |

Exact commands, source provenance, source/test/patch hashes and public reports are bound by state/evidence/ESIMARI-001.json through003. Failed reports and0001 bytes are preserved. Original source is not mutated. Artifacts/esim-profile/ari-*/tests.txt retain all individual failures/subcases; builder.py snapshots retain each test version. The checker does not execute modem commands; its bytes are explicitly synthetic.

Source defects established by actual cases: wrong sequence-byte selection, incorrect nonempty TLV payload slice, missing high-length shift, incomplete packet/TLV extent handling, and mismatch between Packet.pack bytearray output and TLV's scalar fallback. Patches are an offline analysis aid, not a validated arbitrary modem serializer or Samsung bridge. Untested encoder range/unknown-bit behavior remains open.

## Input gap and next step

No actual local selected iOS16.5 image/product/build manifest, CommCenter/baseband library/plugin/cache inputs or relevant entitlements were supplied. This is not a filesystem-wide absence claim. Hardware model documentation cannot determine selected-image component presence or private ABI. Public API strings, later ARI tables, a Qualcomm17 donor and a Settings screenshot cannot satisfy the acceptance.

Current decision: retain the approved first OS/profile, keep ARI/QMI frontend selection unresolved and continue independent ESIM-001 transport/library preparation. The exact supplied-image input requirements and inspection order are in README.md, with a machine-readable frontend-decision.json. Do not invent paths, claim missing standalone libraries are absent from a shared cache, silently switch the OS or download Apple components.

Once explicitly supplied local inputs exist, record acquisition/build/product provenance and hashes, then inspect actual architectures, dependencies, entitlement/service interfaces and matching private/frontend ABI. Qualify an isolated extractor against that image before deriving tables or choosing an adapter. CELL-009 separately needs matching Samsung schemas; native lifecycle tests additionally need transport, agreed test subscription and recovery. Existing production profiles are not fixtures.

This task is blocked on those exact external inputs. Released the finished shared source catalog and implementation-plan reservations through an audited owner transaction; retained narrow source-checker/patch/report paths. KRN-001/KRN-003/NAT-001 original records/reservations remain unchanged. This branch's external gap does not block other host tasks or complete the overall goal. An optional asynchronous request asks whether existing local image/RIL inputs are available and for their paths; no answer has yet supplied an input. Do not infer one from elapsed time.

## Validation

After final state updates, make check passed124 default tests plus registry/board/capability checks. The actual outcome/log/source/patch digests are in fixtures/public/esim-profile/final-checks.json. All three experiment evidence digest sets were verified; prior tasks/experiments, authorization/facts and native capability state remain unchanged. An initial ad hoc comparison mistakenly expected the entire experiments array unchanged; corrected to require all prior entries unchanged plus exactly the three planned additions. No source/test rerun was needed for that verification correction. The seven donor regression groups are a separate actual offline integration check, not seven new default unit tests. No prior unrelated Android or hardware experiment was rerun for this source-only change.
