# Explicit transient paths in reviewed histories

A preserved source history can add a file and later rename or remove it. The
final candidate diff omits that temporary name. Optional `historical_paths`
names those exact additional relative files; older plans default to an empty
list. The union of every commit's touched paths must equal the disjoint union
of final `paths` and `historical_paths`, without duplicates or unused entries.

Both sets receive the same literal-path, forbidden registry/view/lock, primary
dirty intersection, ignored new-file collision and symlink-parent checks.
Exact source/candidate patch mapping, stale-HEAD checks, approval, shared flock
and publication/check supervision are unchanged. This field preserves reviewed
history; it does not authorize arbitrary transient changes.

Prospective experiment `INTGATE-HISTORY-001` executes only disposable local Git
repositories. Verify an explicit add/rename history passes, omitted and unused
entries fail, duplicate/overlapping/noncanonical entries fail, temporary lock or
registry changes fail, historical dirty/ignored paths and symlink parents fail,
and an unrelated mapped source commit still fails. Retain actual CLI exits,
capsules and commands. Reuse the existing light gate suite for lock/stale-HEAD
regression. One serial Python job under 256 MiB; no project common check,
compiler, guest or MAIN Git publication is part of this experiment.
