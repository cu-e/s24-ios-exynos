# Capability and roadmap validation

1. Validate the task registry and generated Kanban with `python3 tools/lab.py validate` and `board --check`.
2. Run `python3 tools/capabilities.py --check` to check source/task links, immutable evidence digests and the generated hardware view.
3. Run `make check`. Capability tests ensure an upstream report, inventory or passing host build cannot satisfy native evidence requirements.
4. Inspect scope/dependency gates: no new device authorization, native XNU requires actual recovery qualification, carrier-dependent tests remain pending, and every subsystem has explicit acceptance.

The matrix is an authored assessment, not an automated truth oracle. Evidence kind/digest validation cannot establish that a report actually proves a particular hardware feature; reviewers assess that before accepting it.
