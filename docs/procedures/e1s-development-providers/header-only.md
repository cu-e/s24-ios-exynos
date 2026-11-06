# STR018 separately admitted native header phase

Original SR18 owner and worktree remain unchanged. Experiment
`E1SPROVIDERHEADERS-004` covers only the 30 genuine native Make install groups
and one Firehose header export from corrected provider plan006. The new
attempt changes seven requested target strings in two Make groups
to retain the exact source-defined dot/empty directory segments. All 315
physical output selections, filter logic, flags and visibility stay unchanged.
The later Firehose compile retains the prior narrow two-token warning
correction. The original
f298410 commit, plan002 and prior header-only drafts remain retained.
Independent review found an alarm ownership/cleanup defect in adapter
`90e31681…` (commit `b35a666`); plan002 and that source revision remain
unchanged. That source-only correction removed the custom alarm and added
monotonic work-boundary checks before any target operation ran.

The exact header plan is
`artifacts/e1s-development-providers/header-plan-007/execution-plan.json`, SHA256
`7484ce35fa5c8b8519baf83973eac1d758b63b96f744ac1e5260c1234c48b1d2`.
Adapter `fixtures/public/e1s-development-providers/header_only.py` has SHA256
`97d201ce8f6cfee9ca2c222fc11a8fe584eaa08155dbcf8e1c9633ae6e41bad2`.
This retained source freeze preceded actual ROOT98 `execute-004`. See the
actual phase receipt below; earlier plans and whole failures remain unchanged. Prior ROOT87
`execute-001` remains unchanged: first Make command exit 2/resource pass,
zero headers, no Firehose export, own reservation released and root observed
zero survivors. Experiment `E1SPROVIDERHEADERS-001` records that actual failure.
The failure capsule is `artifacts/e1s-development-providers/failure-record-001/evidence.json`,
SHA256 `f0f819476abd525e991843d3b5bba6104ef6a9ec0fd9e294fad71769eeedce52`.

The bounded read-only Make database query uses `--question --print-data-base`,
with Landlock writes confined to its separate diagnostic output; no target
recipe ran and raw001 hash stayed unchanged. It proved that the double slash
is genuine. `EXTERNAL_HEADERS/Makefile` sets `EXPORT_MI_DIR = .`, and
`MakeInc.rule` concatenates that literal segment: the rule is
`.../Headers/./stdatomic.h`, while the failed request omitted `./`.
`osfmk/libsa/Makefile` sets an empty directory, requiring the literal
`.../PrivateHeaders//string.h`. GNU Make names distinguish these spellings.
The source-derived correction changes six EXTERNAL_HEADERS targets and one
libsa target; all other command tokens stay identical after fresh-output
remapping. Exact before/after evidence is
`artifacts/e1s-development-providers/target-spelling-correction-001/delta.json`,
SHA256 `cdfb279239cab82001f3185fd0ffeb64ad30d129c1f7e4592a6f3685b9eba45d`.
There is no new filtering or header retry in this freeze.

ROOT90 then attempted the exact target-spelling correction in `execute-002`.
The first operation resolved its target but failed exit 2/resource pass because
standalone `MakeInc_cmd` had no `MKDIR`: Bash tried to execute `./kincmidir`.
No filtered headers or Firehose export resulted; own reservation released and
root observed zero survivors. `E1SPROVIDERHEADERS-002` records this actual
failure once. Capsule002 SHA256 is
`d9833bfd7453de485b3630c36f0648960c5a6eea930b65664988536a78723ce1`;
raw002 SHA256 remains
`bb423444a5fb97e8aecd2549666f950b181caac6e8891b3dc8b83c4772b20096`.

The separate `header-host-commands.mk` retains the immutable STR011 standalone
query/platform map and binds actual Linux TR/BASH/ECHO/PRINTF/MKDIR/RM/INSTALL
executables, plus native source-exact ERR and header logging expressions.
That retained first map had SHA256
`08d2a410d60a948ac3b9f0beafd67404c51db080d934551ef7bc59853ca78f44`.
`host-command-provenance.json` binds the native MakeInc.cmd assignments, real
executable paths/argv/hashes, native installfile source and existing historical
Linux install compatibility; SHA256
`4f9f13e260f0e3b30a394fa3b0d454a53c092b8e1640a5b82288de50ae99880d`.
GNU install receives unchanged `-c -m 0444`, previously qualified for this
header grammar. Native rule/filter/profile/selection semantics are unchanged;
no old installed header is adopted and no new host tool is built.

All 30 requested native Make recipe expansions passed a bounded read-only
`--dry-run` query in a separate Landlock-confined diagnostic context (62.5s,
one child at a time, 256MiB ceiling, 120s source-work budget). All 12 required
command expressions were nonempty in every group. Four actual MIG prerequisites
were copied only into that diagnostic context to resolve genuine source rules;
no recipe, filter, install, compiler or archive ran. Query evidence SHA256 is
`481de07fd4b8c2cb08bd57ca1201e11d1c1c3bb3561fbbda0f4d6d853de826fb`.
After fresh-output remapping, the only argv changes are 30 `MakeInc_cmd`
operands. The existing 653 input bindings are preserved except the owned route
fixture, with 11 added host/provenance pins. All 315 physical selections,
32 native flag guards, first31 operation identities and resource bounds remain.
That source acceptance preceded ROOT94 attempt003; its whole failure is
retained below. Fresh execute004 requires a new review and exact root grant.

ROOT94 completed 30 Make operations at exit 0 and the genuine Firehose export
at exit 1, all 31 resource passes. All 315 nonempty regular 0444 headers, four
hash-identical MIG prerequisites and the actual `14be8d31…` Firehose export were
observed. Nevertheless whole attempt003 is FAIL: every native signature lacked
13 expected platform selectors, and the old guard read native terminal NUL as
an extra argv token. All 664 inputs stayed unchanged; own/root reservations
released and root observed zero survivors. These 315 bytes are not qualified
under the intended native filtering. Failure capsule SHA256 is
`1446e3060185ba1d5ed6144270d96629afebd3153258f82107b0d038352d87a5`,
with detailed verification `failure-record-003/verification.json`.

The corrected map appends the three exact native MakeInc.cmd assignments at
lines 250/251/254: complete embedded, simulator and combined supported-platform
vectors. MakeInc.def1061 then derives the intended 13 platform filters. This
states a source-defined filter token universe, never SDK availability. Current
map SHA256 is `bd8be06ebc2cd10924a7d2ee9b2195bde4c07cae9dcabdc154f468b45b48f91c`;
current provenance SHA256 is
`6ed54569fdc21aabd1a71fbffaf8639301da344988079e4a376af215f542c2d1`.

Native SETUP/replacecontents counts and writes a final NUL after its newline.
The narrow caller decoder requires that exact single-NUL storage grammar and
canonical space-joined argv, then compares the full expected argv unchanged.
No generic trimming or missing-flag tolerance is introduced. Read-only decoding
of all 32 real003 signatures still rejects their missing 13 platform flags.
The new source query expands all 315 intended native unifdef invocations with
13 platform plus 13 privacy flags (one public, 314 private) in all 30 groups.
Query evidence SHA256 is
`889e87318dd74fcd8d7f9bee6fb249cd508a4a27ffe480fd3247791ad26b8af9`.
This is prospective source evidence; actual004 Make/unifdef argv, 32 signatures
and fresh bytes must be independently verified after a future admitted run.
No actual004 filtering, compiler, archive or layout operation has run. All 37
command vectors and 315 selections are unchanged after fresh-output remapping;
only the map/provenance/route inputs and native signature decoder changed.

The adapter uses existing 9929 `project_approval`, ProjectBudget, run_child and
the accepted qemu_host supervisor, plus existing 9f80 `owned_cancellation` and
`run_owned_child`. It implements no process launcher, monitor, signal cleanup
engine or budget broker. Root approval must bind this exact adapter/header
plan, original owner, task, experiment, `providers-headers` slot and fresh output.
One serial slot with 512MiB ceiling and the existing 4GiB memory floor remain
unchanged. The adapter's `whole_seconds=600` is a dispatch/work-boundary budget,
not a hard whole-process limit. Monotonic checks run at each hash, copy,
directory, product and command boundary. Each shared child receives a timeout
of `min(120s, remaining work budget)`. The pinned common helper first performs
stable-memory admission for up to 45s, before starting that child timeout clock.
A final admitted command may therefore finish up to 45s after the 600s work
boundary (645s admitted work), followed by finite owned reservation release and
evidence cleanup. No subsequent work is dispatched after the boundary.

Root must supply the external GNU `timeout` watchdog at 690s before admission,
with root-owned cleanup verification. The adapter does not install or enforce
that outer watchdog, and its declaration is not a grant. The adapter installs
no alarm or timer; existing shared bounded locks retain their own alarm
ownership. Existing cancellation handlers remain installed through finite
owned cleanup. Header-plan003/82b3 and adapter dfab receipts remain retained;
the retained deadline-only revision changed source documentation and metadata.
No grant, allocation or permission is inferred from these declarations.

Setup is restricted to canonical owned header directories and exactly four
hash-identical actual003 export-header prerequisites from final MIGfe67, copied
read-only into genuine Make generated prerequisite cwd paths. No native BSD
projection, object directory, SDK directory, compiler, archive or layout setup
is part of this phase. Children have the existing run_child Landlock write
boundary covering the owned output; native Make source/host inputs remain read
only. All 665 frozen provider-plan inputs and the exact helper files are checked
before target tools and after the header phase.

Each actual Make exit and combined child/resource/cleanup record is preserved.
Genuine Firehose unifdef accepts 0 or 1, with its raw exit retained. The adapter
requires 315 real nonempty regular0444 installed headers, physical hashes and
source/mode provenance, then checks 32 actual .UNIFDEF_FLAGS files against the
current public/private native filter argv. The Firehose export receives its own
actual path/hash. Native filtering and empty seed remain unchanged.

Missing output is recorded as `absent-filtering-unproven` and fails closed. Make
exit 0 alone never labels an absence genuinely filtered-empty, and no empty stub,
old header or raw fallback is inserted. A failed or inconclusive run retains
its partial files and diagnostics; there is no automatic retry. Actual filtered
bytes and any new missing/empty boundary must be reviewed before four compiles.

Existing cancellation and budget release validate owned child cleanup. The
adapter releases only its own reservation; root owns the allocation/global
lease. Planned raw evidence is `execute-004/evidence.json`; prior raw001/002/003 remain
retained. A passing header
result qualifies only the observed header phase, never provider objects,
archive contents, ABI, full link/image, runtime or hardware. Original task
completion remains gated on later actual provider results and independent/root
integration acceptance.

Future invocation requires the root-owned external GNU `timeout` 690s watchdog
and explicit root-supplied approval path and digest. The adapter argv below is
the inner invocation; root supplies and owns the outer watchdog:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  fixtures/public/e1s-development-providers/header_only.py \
  --source-plan /home/egor/dev/pet/s24-ios-exynos/worktrees/str-018-e1s-development-providers-20261106/artifacts/e1s-development-providers/header-plan-007/execution-plan.json \
  --source-plan-sha256 7484ce35fa5c8b8519baf83973eac1d758b63b96f744ac1e5260c1234c48b1d2 \
  --approval ROOT_APPROVAL_PATH --approval-sha256 ROOT_APPROVAL_SHA256
```

## Actual004 header-phase receipt

ROOT98 executed this exact header plan and caller. The verified actual header
descriptor is `fixtures/public/e1s-development-providers/generated-headers.json`,
SHA256 `07724b361a15671a7a31d5f14daf11b4d892dc732d0f181cfd780c7223c97fbe`.
Raw004 SHA256 is
`fdb4d40a27ac4180cf0a90c755ed0c484261f6c619f1dfeffe115d7c5a5b7749`.
All 315 physical regular nonempty 0444 headers, 32 exact full decoded native
flag signatures and four exact MIG prerequisites were independently read and
rehashed. Actual stdout proves 315 native unifdef invocations with 13 platform
and 13 privacy flags (one public, 314 private), plus the separate genuine
Firehose export `14be8d31…`. All 665 inputs stayed unchanged; all 31 commands
passed resource checks, own/root reservations released and root observed zero
survivors. The actual phase capsule is `pass-record-004/evidence.json`, SHA256
`d9c31e9644b8cd31fcb76628cc6fe491230864592c3cdf3d8e8af3f370beee2a`.

This qualifies only the observed native header phase. Remaining four genuine
TUs and two archives require a separate source freeze and root allocation.
Actual MD, CPU/cluster tuple/layout and archive contents remain required;
provider ABI, full link/image, runtime and hardware are unqualified.
