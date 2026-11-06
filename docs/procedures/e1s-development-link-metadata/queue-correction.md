# Additive STR032 queue correction

This supersedes only the first caller's queue transaction handling. The original
`50b67be3bbd78f87325079e127a472e4360616c0` packet, `run.py`, source plan,
control inputs, README and evidence retain their bytes. CM found two concrete
source blockers there: queue publication preceded cancellation/try-finally, and
shared queue writes directly truncated the live file. No target execution ran.

`input-2.json` binds the additive `run-2.py` and the unchanged 37-command plan.
The metadata recipes, input pins, all prior data/parser functions, three phases,
256 MiB/20s/180s limits and conservative clear-queue predicate are unchanged.
Root must supply/review an exact new caller grant, use the existing external
finite watchdog, and execute only in an idle queue window. No helper is edited.

Owned cancellation and the outer try/finally now precede admission. Publication
and local registered bookkeeping are inside cancellation cleanup deferral.
Shared writes create a fresh same-directory temporary file, preserve queue mode,
flush/fsync its bytes, atomically replace the queue and fsync the directory under
the existing integration lock. Failed temporary writes leave the old queue intact.

Cleanup always reads the queue afresh under that same lock. It releases only a
slot equal to the complete exact owned lease. Thus an exception after actual
replacement but before local bookkeeping still finds/releases that lease. An
altered same-ID lease fails closed; another owner's slot and all unrelated/new
queue fields remain unchanged. An evidence/hash exception cannot bypass lease
cleanup. A live owned session retains the lease for root investigation.

The queue release receipt names final evidence but marks its hash pending final
cleanup (`evidence_sha256: null`); root binds the finalized raw bytes after signals
and release are recorded. The queue receipt's preliminary outcome is routing
metadata; final raw evidence determines the whole experiment outcome. This avoids
claiming a stable raw hash before the final cleanup record exists.

The focused source/host transaction control passed 35 checks using actual local
temporary queue files and the accepted cancellation helper. It exercised partial
write refusal, actual post-replace exception before bookkeeping, real own SIGTERM
during publication, real own SIGINT during release, handler restoration, exact
lease matching, fresh unrelated-field preservation and busy-queue refusal. It
also compared unchanged metadata function ASTs and original caller/plan hashes.
No real queue, grants, generator, converter or child process was used. Current
Python image HWM was 24,154,112 bytes. This is source transaction qualification,
with no actual metadata/serializer/SDK/provider/ABI/image/hardware credit.

Next: CM review this exact additive diff; root alone may grant/run the desired
phase. The original serializer gap and all 37 ABI obligations remain as stated
in the first README. STR032 remains open.
