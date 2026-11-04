# Focused radio/donor research procedure

Read research/sources.json and the selected task. Acquire GitHub sources through `tools/sources.py fetch ID...` at full revisions; verify origin, HEAD, clean state and reviewed-file hashes. Expand only reviewed sparse source/documentation paths. Do not fetch submodules, SDKs, firmware or example proprietary RIL binaries. Do not run upstream installation, flashing or automatic real-device test scripts.

Use the connected Reddit MCP read-only. Record query timeouts separately from empty results. Feed fallback uses an archive; preserve IDs and cursor, deduplicate against the existing 324-post archive, and distinguish titles, self-text, selected comments and actual linked implementations. Removed content and missing comments cannot establish a working feature or its absence. Keep complete third-party snapshots in ignored research/snapshots; publish minimum derived observations and provenance.

Inspect source-level ABI/transport boundaries and licensing before choosing a donor. Distinguish source review, host execution and native acceptance. Models run only from an isolated artifacts copy with a finite process deadline, actual compiler/flags and retained failure/pass logs. A donor's test pass is not the phone's hardware result.

The radio follow-up found two additional gates: verify the selected iPhone X/iOS16.5 frontend for eSIM (ESIM-004), and recover the exact Samsung vendor command schema from explicitly supplied local inputs (CELL-009). BaseMirror's static analyzer is a research candidate; its device-testing half is outside scope. FirmWire is a candidate only after exact supported SoC/firmware and host dependencies are verified.

```sh
python3 tools/sources.py verify qcom-baseband lpac scion-avf iosplus10 ios-lemonadep base-mirror firmwire s24-linux
python3 -m unittest discover -s tests -p test_cellular_framing.py -v
python3 tools/lab.py task show CELL-009
python3 tools/lab.py task show ESIM-004
make check
```
