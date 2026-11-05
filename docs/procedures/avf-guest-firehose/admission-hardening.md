# VM-020 frozen argv admission hardening

Owner: `codex-guest-exec-20261106-cx`. This correction follows the platform
integrator's independent reproduction against original commit
`76db6b216fcb03c0e2035d37760464acbaca89ca`: appending `-UDEVELOPMENT` to the
selected `bsd/subr_log.o` guest row passed `validate_guest_row`. The original
emitted recipes were correct and no compiler ran. The defect was incomplete
admission of subsequent altered recipe data.

`validate_guest_row` now requires SHA256
`cf737937e6e6c74f00302f2bebcc1ec6a08329fb48ab35b451dd226f590113ca`
of the complete 261-token selected argv array, encoded as compact ASCII JSON
with `ensure_ascii=True` and `separators=(',', ':')`. The digest comes from the
actual immutable VM008 manifest bound to SHA256
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
All existing source, configuration, namespace and output-template checks are
retained. No flag, token order or template output mutation is admitted. This
check occurs before the producer's already declared source/include/output
transformations; it does not introduce an execution route or a component ABI.

The original three emitted provider/layout/interface recipes and old source
runs remain byte-for-byte unchanged. The preserved plan digest remains
`f6c1f5ef1dd60353ae887bc257f0c900f0c8ba0fdf8f5bb1c3e31c62b940b197`.
A separately accepted executor must freeze these recipe tokens and permit
only the original `-o`/`-MF` `@OWNED_OUTPUT@` values to become admitted owned
paths; no arbitrary appended options or profile changes are authorized.

Focused command:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -B -s \
  docs/procedures/avf-guest-firehose/admission-controls.py
```

The command returned exit 0. The actual unchanged row passed. Fourteen actual
negative controls rejected appended development/board/allocator/private flags,
split `-D` syntax, target changes, an include, a response file, deletion,
reordering and an output substitution. The same command executes the original
committed predicate to preserve the real earlier `-UDEVELOPMENT` acceptance.
The final current capsule is `admission-controls-session2.json`, binding the
old source bytes, unchanged plan, new producer/controls, manifest and observed
results. Session1 is retained; its command representation omitted the actual
`-B` option, corrected to `sys.orig_argv` in session2. Its measured predicate
outcomes were unchanged.

No source/header preparation run, source matrix, compiler, archive, QEMU,
phone action, repository common check or MAIN publication occurred. Only the
manifest and the predicate's selected source/configuration inputs were read;
there was no full source/header rehash. The new producer source differs from
the historical source-evidence builder digest; that original evidence and its
historical validator remain preserved as records of the original build.
The focused capsule is the evidence for this narrow guard change.
Independent recheck and an accepted executor remain required before execution.
