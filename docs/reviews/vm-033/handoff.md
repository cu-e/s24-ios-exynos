# REV-046 handoff

Owner `codex-review-guest-allocator-20261106-fa`; actual atomic claim REV-046
reported before worktree/controls. Worktree `worktrees/rev-vm033-fa-20261106`,
branch `team/rev-vm033-fa-20261106`, base
`b000b0af2e67212e4c75a217f2b38467e820268a`. Only `docs/reviews/vm-033` is owned.
Original VM-016 worktrees and producer VM-033 implementation remain untouched.

The exact producer chain 544ba087 -> 78cc7ad9 -> d9e236a4 -> 9248a9dc and assigned
helper/primary/supplement hashes match. Source reads found exactly the seven
allocator-specific producer files in that chain. The review checker/procedure
were frozen at `c1d22b47bcb3e44844b94b8f017cebf5c25da082`.

REV046ALLOC-001 was registered before the only actual focused run:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s \
  docs/reviews/vm-033/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out docs/reviews/vm-033/runs/review-001
```

Actual exit 0, 35 passed checks, 14 focused rejection cases and 12 owned bounded
copies. Elapsed 2.066027470980771 seconds; actual current-image VmHWM/RSS
25,300,992 bytes, separately recorded from inherited ru_maxrss 1,380,720,640.
Three >=4 GiB available-memory samples preceded the controls. No review attempt
failed. No compiler, archive/link/section utility, producer corpus entrypoint,
generator, guest, phone, common check or allocation was executed/requested.

Independent raw bytes confirm the actual old OSData 192-byte live-support
metadata, six unsigned64 external pointers, zero inline addends and real
`__cstring` names/signatures. Independent kalloc parsing confirms 16 references
to four fixed/variable start/end boundaries and matches every supplement tuple.
Source rules and initial failed ARM64 addend-parser history remain pinned.

The raw review capsule SHA256 is
`2798c57276e13d9ee9369512fbe840a9c57f95836b019b22258d1f1b5bd46397`.
The maintained `evidence.json` wrapper SHA256 is
`cb62aaf0aabac052ae89e884988dbc17561dcc73868a085979cc285d06d7302a`.
All corrupted object copies remain local under runs/review-001 with exact hashes
and are ignored for Git; only review text/JSON/script are committed.

Bounded verdict: accept the frozen two-object preflight, with one disclosed
nonblocking resolver limitation. An owned pointer-addend+1 copy reveals that
producer symbolic string resolution omits the inline addend; the independent
reader rejects the changed name, and production's exact object-hash condition
rejects the copy. All six real frozen pointers have addend zero, preserving the
current observations. Generic future reuse must add inline addends or explicitly
reject nonzero ones. Findings were sent to INT002/root for relay to original DO;
the reviewer did not modify producer source.

Final LTO reachability and linked record/string/boundary retention remain
unmeasured. MakeInc.def dead-strip flags are conditional on USE_LTO=1; string
presence is not selected final-link evidence. Startup consumption and guest
runtime remain unknown. These exact historical afc5-profile objects receive no
new-profile or ABI/kernel/boot credit.

Next: original DO acknowledges the bounded resolver limitation; INT002/root
assess the scoped report and exact commits. Independent review completion and
source acceptance require accepted current-HEAD integration/common checks plus
root authorization. Keep REV-046 and VM-033 open until those gates. DO alone
writes the producer implementation and eventually closes the source task.
