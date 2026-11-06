# STR-001 short Scion reuse audit

Owner `codex-strategy-scion-20261106-sr1`; scope source review only.
Read the user's strategy attachment first. Worktree
`worktrees/str-001-scion-20261106`, branch `team/str-001-scion-20261106`,
base MAIN951f23336c1521c8ee94828e26fc98bfcf1e8411.

Hypothesis: Scion already supplies the generic QEMU/AVF/loader/open PID1 path,
and a bounded exact-source comparison can identify useful changes and a cheaper
next diagnostic without another kernel build or custom executor. Separate
reproduction/environment fixes from actual E1S adaptation and device proof.

Read authoritative local source pins and inspect official current Git refs,
commit comparison and selected code/instructions. Current official repository
name is Scion-Project/scion-kernel (old hackios-xnu-kernel redirects). Capture
exact SHA and source hashes; compare relevant recipes, shim/loader, PID1 and
dependencies to a6f4bc38aa244359cd365c976244a88c9d6b3304. Fetch only bounded
JSON/text into an isolated audit artifact cache. Preserve network failures.
No pinned checkout, sourcepin or ref mutation; no generated build system.

Do not duplicate CM's infrastructure audit, CN's E1S audit or root's HakiOS
audit. Deliver a compact component reuse map, current changes and transition
cost, S24 relevance and one falsifiable cheapest next diagnostic. All claimed
upstream behavior is source-derived unless independently observed locally.
Unavailable hardware facts remain unknown. No target tool/build/phone/common
action is part of this audit. Individual network commands time out at30 seconds;
finish useful decision within a short audit, not a new research program.
