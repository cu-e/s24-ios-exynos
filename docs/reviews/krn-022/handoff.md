# REV-006 handoff — 2026-11-05

Owner: `codex-team-review-pthread-20261105-av`.
Branch: `team/rev-pthread-20261105`.
Worktree: `worktrees/rev-pthread-20261105`.
Reserved paths: only `docs/reviews/krn-022`.
Exact reviewed authored commit: `16a7497ef0243a3c4fbdfa7ec5189a864a6a4f88`
(integrated 3c23af0). Reviewer base is main 3b5b4f9.

Bounded result: no P0/P1/P2 finding within the measured genuine pthread component
boundary. README.md gives source-line assessment and explicit scope limits. No
KRN-022 ownership, implementation, shared reference or main artifact was changed;
REV-006 remains in progress pending coordinator acceptance. Earlier REV-003 and
REV-005 were completed only after separate explicit coordinator acceptances.

PTHPREV-001 was registered in the primary ledger before verification. Actual
reviewer command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-022/reproduce.py review1
```

Exit 0; UTC `2026-11-05T14:09:18.752734+00:00`; nine check groups / 15 actual
subprocess commands. Thirteen exits 0, expected native unifdef changed-output
exit 1, intentional wrong-type compile exit 1. Peak child RSS 70,864 KiB;
sequential compiler commands with 45-second subprocess timeouts. No heavy build,
QEMU/lease use, install, phone/ADB/root/MMIO/flash/reboot or private Apple input.

All 3,578 artifact hash entries across PTHP-005/007/008/009/011/012 matched,
including final acceptance's 21 checks. Independently audited all installed
headers/sources/modes and explicit absent outputs; fresh real thread.h unifdef
matches installed bytes and removes the internal struct body. Independent reader
confirms 140 declarations/284 layout values from actual kernel/kext objects;
fresh full kext TU matches, wrong actual function-pointer type rejects.
Actual allocator records/signature relocations and old-fake-signature control
match their documented distinctions. Fresh real VM alias link matches intended
section/address pairs; wrong real provider is detected. The separate archive/
Mach-O reader verifies all three members, 39 definitions and 61 imports against
actual 982 source/object witnesses and 24,070 kernel exported names, with zero
unresolved imports or definition overlap. All four native MIG identities match;
fresh real native-context mach_vm generation/unifdef reproduces consumed bytes.

Evidence:
`worktrees/rev-pthread-20261105/artifacts/rev-krn-022/review1/evidence.json`

SHA256: `503062615d13cc093aabf05393c4b289f0cb0a8e21742b16b770cf1221324785`.

Report:
`worktrees/rev-pthread-20261105/artifacts/rev-krn-022/review1/report.json`

SHA256: `6ebb6a58c438456c4a7c5f253bc281f6416aa3d02a9872048191655449f4b3d3`.

The report retains exact commands, stdout/stderr, exits, source/tool/reviewer
hashes, capsule identities and resources. Local generated headers, objects and
MIG traces are untracked; committed review files contain no Apple SDK/header or
binary artifact. Existing original evidence and failed runs remain untouched.

Next: coordinator inspect/accept the documentation commit and evidence, then
decide REV-006 completion and the controlled KRN-024 link stage. Preserve exact
BUILD_LTO=0 context, two namespace remaps, native aliases and all required genuine
libraries. No full SDK, private ABI, crypto, full link, runtime or native-device
qualification follows from this component review.
