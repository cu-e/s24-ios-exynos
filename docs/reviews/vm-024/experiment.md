# REV-028 independent raw mockfs review

Owner `codex-review-boot-inputs-20261106-dw`; host-only, no compilation or guest.

Before execution register `REVMOCKFS-001` in sole MAIN registry. Review exact
producer implementation commits 19965c7 + 7a71236 and actual packaging commits
ff41a8e + b716bbd + 2257b31. Independently rehash source, actual output manifests,
raw evidence and selected public/composed declarations. Check actual executable
prefix and zero tail with an independent byte oracle. Run only focused copied
byte/path/descriptor controls via the unchanged packager or its imported parser,
never edit original sources/artifacts or run producer's broad test suite.

Controls: changed/truncated/extended prefix/image, wrong/hash and false execution
claims, nonzero padding (also recompute image hash), wrong entry/CPU/command extent,
symlink/FIFO input, existing output sentinel, wrong provenance, deterministic
copy-race injection against a local private input, unsupported signature bytes
retained explicitly as unvalidated. Preserve unexpected failures as findings.

One Python controller <=256MiB address space, serial children <=10s with new
session/owned timeout cleanup, outer <=120s. Three >=4GiB observations one second
apart before any subprocess. Source/data read-only; Git lazy fetch disabled.
Record command exits, hashes, source pins, actual VmHWM and scope boundary.
`executable_qualified:false` and `guest_executed:false` remain mandatory.

No real mountroot, exec, initial stack, signing policy, PID1, syscall, console,
stop, native or S24 claim. Original reviewer closes only after integration and
fresh common acceptance; executor does not run common checks.
