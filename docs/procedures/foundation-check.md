# Foundation verification

Scope: host. No phone required. No flashing tools are invoked.

```sh
python3 tools/lab.py validate
python3 -m unittest discover -s tests -v
python3 tools/lab.py doctor
```

Expected: validate and unittest exit 0. Doctor lists available tools; a missing Android SDK/QEMU does not block foundation work. An external runner limits verification to 120 seconds. Stop by terminating the host process; there are no hardware changes.

Save actual stdout/stderr and exit codes in artifacts/foundation/. Evidence kind=host-test, origin=local-host. Pass validates registry infrastructure, not hardware boot or driver suitability.
