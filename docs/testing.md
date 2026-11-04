# Testing and evidence

## Evidence categories

| kind | origin for a local result | Establishes |
|---|---|---|
| source-review | upstream / local-host | Findings about a specific source revision |
| host-test | synthetic / local-host | An observed result on the host or a model |
| android-userland | local-device | Results inside Android on the identified device |
| native-device | local-device | Results from a custom kernel on the verified reference target |

Fields alone do not prove truth. A person or agent checks acceptance criteria, logs and limitations. `local-host` does not mean `local-device`. Copied upstream results retain upstream provenance.

## Minimal experiment

Before execution, record the hypothesis, procedure, timeout, stop command and expected observations. The CLI stores the plan but does not run the process or enforce a timeout. A device runner must implement timeout and cleanup before use.

After execution, save evidence.json, stdout/stderr, exit code, commit, tool versions and input versions. Record SHA-256 for binaries and dated inventory for hardware tests. Missing evidence is inconclusive, not pass.

```sh
python3 tools/lab.py experiment plan HOST-001 --task BLD-001 --owner agent-a   --hypothesis 'The loader builds with the pinned toolchain'   --procedure docs/procedures/host-build.md --timeout-seconds 300
# Execute the actual procedure with a timeout and save artifacts.
python3 tools/lab.py experiment record HOST-001 --owner agent-a   --evidence artifacts/host-001/evidence.json
```

This example requires a real host-build.md procedure, to be created during BLD-001. Do not register imaginary procedures or edit recorded experiments. Give each new run a new ID.

## Infrastructure checks

`make check` validates the registry, sources and dependencies, and tests state transitions, evidence category mismatches, path boundaries, concurrent claims and failed experiment recording. Inventory/profile tests cover read-only commands, privacy filters, unavailable data and timeouts. These are infrastructure tests, not hardware driver tests.

Large toolchains, QEMU and the Android SDK are not currently mandatory. Install them when the selected task needs them, not merely to make doctor report every tool as available.

Historical evidence retains its original bytes. English translations are reading aids; see [evidence translations](../state/evidence/README.md).
