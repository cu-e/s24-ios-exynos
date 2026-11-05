# VM-032 public guest IIG source audit

Hypothesis: the frozen 17 public guest IIG pairs have traceable declaration,
record and implementation-provider candidates in the exact 104 selected iokit
recipes, while source inspection alone cannot qualify the 16 implementation
interfaces or selected Apple RPC ABI.

Run `tools/build/avf_guest_iig_closure.py` with `--main` pointing to the sole
primary checkout and a new owned `--output` report path. The tool streams hashes,
does not execute IIG or a compiler, and reads only the frozen VM-008 namespace,
pinned VM-007 composition and existing historical IIG evidence. It inventories
all 104 sources/recipes, 17 pairs, declaration macros, implementation method
references and providers reached through public source includes, and RPC record
text/packing. It preserves historical compile errors separately from guest
results. The report records `/proc/self/status` memory high water marks.

Expected rejection controls mutate only in-memory metadata: source hash,
generated hash, a missing recipe, a changed target and a missing typed-builtin
contract. Each must exit 2 with a specific rejection. No immutable input changes.

Acceptance is the reproducible source audit and explicit unresolved gates. A
missing lexical candidate is a finding to investigate, not permission to invent
an SDK record or alter an active source owner. Exact C++ conditional/type checks,
object compilation, RPC layout and dispatch/marshalling require separate
admission after VM-008 acceptance and root resource permission. Main publication
and common checks belong to the permanent integrator.

Initial audit-1, audit-2, audit-3 and controls-1 are retained development checks
made before this registered final replay plan. They are not retroactively
presented as planned experiment executions. The final replay uses the frozen
reviewable tool revision and preserves its actual commands and exit codes.
