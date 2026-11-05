# Platform integration protocol and first candidate

INT-003 owner `codex-integrator-platform-20261106-cn`, worktree
`worktrees/int-platform-20261106`, branch `team/int-platform-20261106`.
Reporting is confined to this directory. Integration may replay exact scoped
component/review commits in this isolated worktree; no stale worktree registry,
generated view or original-owner state is copied to MAIN.

PLATINT-001 prospective procedure:

1. Admit light verification only with MemAvailable >=4 GiB. Inspect the exact
   KRN-036 six-commit series09111a9..b9fa5ca and independent review
   `8b961ac546f9819ae231cdfd5df40fe6d6f7cb73`. Verify declared scope, dependency
   status/source identities, actual implementation capsule SHA256
   `a95b5c69a14519bc2cfc2da8dea025a684bda3a82647b27e66d93d90109afc57`
   and review capsule SHA256
   `19069702c8083d8428dfda91bd337708449ceec86f7a0907d4792a84236fae3c`,
   every relevant source/artifact/continuation binding and actual result logs.
2. Replay only those accepted scoped commits in the isolated integration
   worktree, record original-to-candidate identities and exact changed paths,
   and verify final component/review bytes. Do not rerun algorithms, guests,
   compilers or a full kernel build. Preserve production native
   `__memcpy_chk` closure and NFS ignored-return integration gates.
3. Coordinate with INT-002's single `tools/integration_gate.py`. All operative
   fresh-MAIN-HEAD/path validation, approved FF-only publication and the one
   common check share **MAIN/state/.integration.lock**, distinct from
   `.lab.lock`. Never hold the lab lock across a common check. Preserve
   unrelated dirty MAIN ledger/views; reject staged changes, dirty path
   intersections, forbidden registry/generated candidate paths and stale base.
4. Prepare a concrete frozen plan/candidate and report its hash/cherry-pick
   mapping to root. MAIN publication and common checks require root's explicit
   authorization of that concrete plan after the shared gate is established.
   If MAIN advances, refresh/revalidate the candidate and approval before
   publishing. Hold the same integration lock continuously from final checks
   through publication and common check; report any failed published state,
   without implicit rollback.
5. Record actual dated commands/exits, commits, tool/source/output hashes,
   admission, evidence and handoff. Only original component/review owners close
   their accepted tasks. INT-003 remains active as the platform integration role.

KRN-039 is eligible only after REV-022's final independent review. Provider,
native/private ABI/FIPS/side-channel and full-kernel gates remain explicit.
No phone, root, MMIO, flashing, global installation or heavy run is authorized.
