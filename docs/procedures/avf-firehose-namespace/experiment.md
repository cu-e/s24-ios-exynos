# AVFFHNS-001 source-only namespace qualification

Hypothesis: the genuine pinned public libdispatch kernel header can be exported
at its canonical private install layout in a new immutable root, with exact
same-slot root substitutions producing a new complete guest namespace,
1080-row manifest and versioned object keys while all historical inputs remain
unchanged.

Command from the VM-038 worktree, using a fresh output directory:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -B -s \
  tools/build/avf_firehose_namespace.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --output /home/egor/dev/pet/s24-ios-exynos/worktrees/vm-038-20261106/docs/procedures/avf-firehose-namespace/qualification-session1
```

This executes only read-only Git source checks and one small public unifdef
export. It records exact commands/exits/timing, streamed hashes, failed
controls, old absence proof, new input bindings and current-image VmHWM/RSS.
Register the host-test experiment before execution. No compiler/archive,
header/source build matrix, QEMU, physical device, common check or MAIN
publication is part of this experiment. Passing source-only evidence does not
prove an OSKext/log object builds or its ABI is correct; those remain separately
reviewed, leased consumer work. Preserve every failed/inconclusive run.
