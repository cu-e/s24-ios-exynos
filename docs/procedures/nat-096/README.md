# NAT-096: quiet Stage A image (`loader-diag-xnu-sq-md1`)

Host build, package, driver derivation, tests and mutation pass. Evidence kind
**host-test**. Nothing here ran on the phone.

## Why this image exists

NAT-093 (decision 0036, inconclusive, Stage A row A8) delivered the whole root
and let Apple's launchd run, but the kernel-log window the project can send
back (an 8 KiB head and a 32 KiB tail of the kernel buffer) was filled by one
message: Apple's `lsd[21]` asked the kernel for a CPU monitor above the cap
about ten times a second, and the kernel printed
`denied attempt to escape CPU monitor (missing required entitlement).` each
time (235 of the 243 timestamped tail lines; `docs/procedures/nat-093/`).
`lsd` is an on-demand job in the Stage A plist set, so the smallest change that
takes the flood out of the window is to leave its plist out of the small root.
That is the only change against NAT-092's image.

## What is built

* `build.py` is NAT-092's wrapper with the image name `loader-diag-xnu-sq-md1`
  and the command-line tag `NAT096-sq1` (same length as `NAT092-sb1`), and the
  small root (md0, 4 MiB APFS) built from `stage-a-nolsd-jobs.json`: NAT-089's
  job table without `com.apple.lsd`. The directory holds 18 Apple plists plus
  `com.nat085.ps.plist` (the heartbeat that prints `ps -A`); self-starting Apple
  jobs are the same seven as before (containermanagerd, distnoted.xpc.daemon,
  fseventsd, logd, mobile.usermanagerd, powerd, runningboardd).
* `derive96.py` derives `session_nat096.py` from NAT-092's driver by 9 counted
  substitutions (`--check` compares the committed driver with the derivation).
  The driver is the only launcher, keeps a one-shot marker per image name and
  reads a per-image decision file. Its registry gate is NAT-089, NAT-092 and
  NAT-096 and, if NAT-097 is done before the run, NAT-097 as well.
* No time rule, receive phase, sender or companion changed: receive cap 240 s,
  `loader_return_after` 60 s, deadline 360 s.

## Hashes

| What | SHA-256 |
| --- | --- |
| RECOVERY image written to the test slot | `7595b87752f0e561ada990e1bd7e4bbbdfc1c236198c80f364f49dcd07416da9` |
| packaged `Image.payload` (loader + XNU payload + ADT + small root) | `5f52765e57da98ab897d321f15aa2192fc0469cff3cc3f55ad32e22138fa88ec` |
| loader-only `Image` | `2b7db59e27b37c20f7ed0f66b2a4ea8ce770d878d2e1ca50aafb3daf75ae33f9` |
| small root (md0) | `62801cecc5cdf1e2bfaff8c056bd02e2539295e516fe2011b82fa3d2a5a37057` |
| `session_nat096.py` | `80e2cc272bd7c172d1b04dc036e6a8d5f051b4fca53a9390c6d0fc15581ae22e` |

## Checks

* `test_nat096.py`: 40 tests, all pass. They compare the built payload with
  NAT-092's byte for byte (the command-line tag and the md0 region differ and
  nothing else after the loader; the loader differs only where the image name
  is encoded), check the small root's tree file by file against NAT-089's Stage A tree, which NAT-092 used (the lsd
  plist is the only one missing), and check the driver against its derivation.
* `mutate_nat096.py`: 111 candidate mutants of `build.py` and `derive96.py`,
  one pass, 4 jobs, 1.5 GiB per-process address-space cap, 120 s timeout;
  **107 killed, 3 survived, 1 did not parse**. The three survivors are
  NAT-092's three (a `sys.modules[name] = m` statement and the indentation
  literal of a JSON file written for the record); they are examined and
  explained in `equivalent.json` (`mutation.json` is the annotated result).
  Unexplained survivors: 0.

## Evidence levels

| Level | State |
| --- | --- |
| code written | yes |
| built | yes (host build, package, hashes above) |
| checked in a model | tests and mutation pass on the host |
| ran on the S24 | **no** |
| showed real iOS UI | **no** |

## What this does not show

That removing `lsd` takes the flood out of the log, that no other daemon floods
the same way, that any Apple daemon but the heartbeat runs, or that a
delivery completes inside the cap. A native run under its own decision file
measures that; the decision is written and committed before it.

## Files

`task.json`, `build.py`, `derive96.py`, `session_nat096.py`,
`stage-a-nolsd-jobs.json`, `test_nat096.py`, `mutate_nat096.py`,
`equivalent.json`, `mutation.json`, `evidence.json`. Build and package
artifacts stay under `artifacts/nat-096/` (gitignored).
