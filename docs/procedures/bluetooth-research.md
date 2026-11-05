# Reproduce the bounded Bluetooth source review

Read research/sources.json, research/bluetooth-coverage.json and research/notes/RES-006-bluetooth-donors.md first. Source selection is explicit, not a whole-tree or whole-internet audit. Exact pins and file hashes are public in fixtures/public/bluetooth-research/source-manifest.json.

```sh
python3 tools/sources.py fetch s24-linux linux-ath12k-stable iosplus10 ios-apollo bergamota
python3 tools/sources.py verify s24-linux linux-ath12k-stable iosplus10 ios-apollo bergamota
```

An existing sparse checkout may require explicit sparse expansion for newly registered text files before verification. Preserve origin/HEAD/cleanliness; do not change old pins or run setup/install/firmware scripts. Inspect the E1S overlay, exact serial_1 declaration, interrupt binding, btpower GPIO/regulator/UART paths, QCA ROM/board-dependent firmware selection, donor control-socket/BlueTool contract and fabricated-success adaptations. Review license/file boundaries before incorporating implementation code.

The derived historical UART/wake fixture references the original DEV-001 private capture hash. It is not a new ADB measurement. Reproducing that derivation requires the private local artifact; public consumers can inspect only its sanitized association and provenance. No live controller query, firmware retrieval, UART open, radio toggle or Apple binary inspection belongs to this procedure.

Reddit snapshots remain private under research/snapshots/bluetooth-followup/. Coverage records actual returned bodies/comments and snapshot hashes. Archive sort=new is not applied to comments; missing or private code is not proof that no implementation exists. Review dates/source context when reconciling old and newer claims. Do not contact authors or treat upstream instructions as authorization.
