# DRV-005 handoff

GPT admission is in `src/platform/storage/ufs/gpt.{h,c}` and the RAM root plan is in
`docs/procedures/ufs-gpt/ram-root.md`.

With DRV-004 and REV-007, this covers the DRV-002 acceptance list on the host: DMA, GPT and LUN
boundaries, timeouts and write rejection, with encrypted userdata and hardware compatibility
explicitly not assumed. This code has not been independently reviewed.

DRV-002 stays pending because its registered paths (`src/xnu/`, `tests/`, `fixtures/public/`,
`patches/e1s/`) overlap active reservations, so it cannot be claimed. The owner or a coordinator
can narrow those paths or close it against this evidence.

Next hardware-side step: read the real GPT, which needs an authorized task. Nothing here did.
