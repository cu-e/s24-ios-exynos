# VM-019 grant30 pre-compiler refusal

Original owner `codex-guest-exec-20261106-dd` executed the exact VM-019 direct
`python3.12 -s` launcher argv in root grant30 once. Receipt SHA256:
`639fa3c34d4ccd25d406d1a5f2bdc8b44c8976a7c7cddb2eca950256c80f139a`.
Canonical EV helper 9929, unchanged 1200-second launcher 64e7, allocation
77a7 and VM-019 approval 247546ff all matched their exact root pins beforehand.
The original actual experiment was PLANNED and its output absent before launch.

The direct process exited 1 immediately. Engine start metadata:
`2026-11-06T07:31:45.745961+00:00`. Error:
`ValueError('Root allocation/queue must be canonical MAIN artifact paths')`.
The approval's root_lease_path points into the integration worktree rather than
canonical MAIN artifacts. The admission gate rejected it before ProjectBudget
reservation or any compiler. No retry, path correction, resume, flag/source/cap
change or global release was performed by the worker.

The process ended before a PID/session could be observed through the first
post-launch tool query; that identity is unknown, not inferred. The exact
experiment process scan then found no live target. Allocation30's reservation
state and budget lock files were absent. Engine compiler flag is false, with
zero commands and zero objects. Current executable-image VmHWM: 31,125,504 bytes;
the larger inherited ru_maxrss remains separately reported.

Preserved raw artifacts in the security artifact root:

- `wave30-launch.stdout.txt` SHA256 `807eed82ecb56e040a487e024cc4480766fb05381458f19cb86ab0db0e325f8f`.
- `wave30-launch.stderr.txt` is empty, SHA256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- `wave30-launch-record.json` SHA256 `e8629e638a482e1f30e1fee849219ac999ae4f0c2005f9c4477482aa0b847672`.
- `wave30-terminal-status.json` SHA256 `4a7e305c27754e8b18ba347ef4fd6bf04d8f16f6255f62411a5a320cfea19a04`.
- `final-resource-execute-001/runner/evidence.json` SHA256 `a4cceb18ceb83636428327ebfef9eeabcb4a3161e6cd2fc10fb6ea0e10001cee`.

The first output contains only the exact executor copy and its failure evidence.
Root received terminal raw hashes, cleanup and reservation facts before this
documentation. Root then explicitly instructed recording the refusal once and
registering a distinct future actual experiment/output. CLI exits were both 0:
`VM019FINALBUILD-001` is RECORDED FAIL and `VM019FINALBUILD-002` is PLANNED.
The latter uses fresh absent `final-resource-execute-002/runner` under the same
security artifact root. Source plan ced65ff9 remains unchanged and is not rerun.
See `final-resource-build-002.md`; no compiler before the separate root31 grant.
