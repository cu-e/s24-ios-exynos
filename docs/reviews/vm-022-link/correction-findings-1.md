# REVMAIN-002: corrected core needs cursor cleanup

Original EU owner reviewed exact corrected freeze
`9fd4b19765b4c5e2f12147dc1d3ba37ea772295d`, helper
`0631a7d8f310e881d08105c4229c1e22ccb771eb52453648e0a1f1aae4c18464`.
The focused independent Python/tempFS command exited 2: 97 checks, 95 pass,
2 fail, 0.431 seconds, current-image HWM 114,827,264 bytes. No child process,
target tool, productive allocation or unchanged benchmark repetition occurred.
All 203 producer artifact pins were verified. The prior failed review is intact.

Both failures concern **partially consumed borrowed symbol iterators**. A real
two-symbol MH_OBJECT was parsed with the actual `macho_snapshot` API. Inside
the context, create `iterator = view['external_symbols'].items()` and consume
one row. After leaving the context while retaining that iterator, `index.db`
is None and its temporary directory is removed, but a real descriptor still
points to `/tmp/vm022-symbols-.../symbols.db (deleted)`. `values()` produces the
same result. Closing the iterator releases that descriptor; the reviewer did
so and confirmed exact descriptor-baseline restoration in each case.

The baseline already includes the `/usr/lib64/libffi.so.8.2.0` descriptor.
The additional deleted database descriptor is a distinct real observation.
Calling SQLite connection.close does not finalize every retained active cursor.
The snapshot must own and invalidate/finalize these cursors before closing the
connection, including normal, exceptional and cancelled exits. Merely clearing
the connection attribute or deleting its path does not close the descriptor.
No mock read, fabricated database or rejected production call establishes this
failure: the actual SQLite cursor and file descriptor were observed.

All original FD/path/byte/digest, transformed EOF, final section/parent/file/VM
and file-backed entry failures now pass. Key/owner/task/literal reservations,
compiler and child-start checks derive from actual explicit historical AF193
APIs and reject contradictory fixtures. Typed receipt and closed profile/
completion guards pass. Actual own-process SIGTERM and ordinary exception
unwind the borrowed snapshot, close its index, restore descriptors and restore
the previous handler when no cursor remains suspended. Primitive convenience
results do not leak a lazy index. The unchanged compact-index/name/nlist-loop
AST and measurement bindings were independently compared to the once-measured
700,000-symbol run; that benchmark was not repeated.

There is a separate source integration issue: the intermediate stage emits
`outcome='incomplete'`, while the ledger evidence envelope accepts only pass,
fail or inconclusive. No actual target run reached that issue because productive
profiles remain empty. Use the schema-valid inconclusive result with explicit
`complete_link_product=False` and the unresolved allocator/runtime gates.

Reproduction source `correction.py` SHA256
`fcf86662fa5a72447865d5b65415ab822874c779bb1db55ad0c83b5900d0518f`;
actual report `artifacts/rev-vm022-link/correction-1/evidence.json` SHA256
`9b422a87be7e61d7a5d4a21f2cff54d10eef684e4cd3425b8afc0e71d02e7233`.
The source contains exact fixture bytes and real mutation/iterator barriers.
All paths are in this independent review worktree unless stated otherwise.

Original CU, root and INT002 received the concrete findings and hashes. Next
dependency is a separately frozen cursor/schema correction, preserving this
0631 freeze and all failed raw evidence. Runtime and allocator modules remain
owned by VM-047/VM-048; their closed completion/profile pins and source-qualified
actual witnesses are still required. No complete link/image/runtime, execution
grant, task completion or publication follows from these controls.
