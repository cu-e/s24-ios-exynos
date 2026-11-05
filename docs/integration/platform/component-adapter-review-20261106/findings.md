# Corrected VM-036 review: fixes required

The frozen adapter SHA5152e733 at ada7eb2 is held for three independently
reproduced P2 findings. Its quarantined process policy prevents current actual
component execution. These are product-validation defects to fix before that
gate is opened; they do not claim a real compiler/archive run or unsafe guest.

| Finding | Source location | Actual bounded counterexample |
| --- | --- | --- |
| P2-1: mixed object identity | `object_details`, line 362 | Real helper validates/hashes the real guest bootargs negative-control object; deterministic pathname replacement occurs before the adapter reopens it for symbols. It reports the guest object's SHA6337d928 with borrowed native Firehose exports. Restoring the original guest object leaves matching accepted SHA but no required provider export; `inspect_archive` still accepts those wrong member bytes. |
| P2-2: hidden foreign archive member | `archive_members`, line 444 | An ordinary additional `__.SYMDEF_bad` member contains arbitrary non-symbol-table text. The broad prefix skip omits it, so the exact-member gate accepts an archive with unreported extra content. |
| P2-3: executable omitted from runtime integrity | `runtime_snapshot`, line 299 | An owned copy of actual qualified libtool starts at e9b54427. Appending bytes changes it to d360c168, while both real runtime snapshots pass and compare equal. The executable is absent from content/identity bindings. The real original remains unchanged and the copy is never executed. `prepare` prehashes tools, but this omission leaves the post-command comparison unable to detect executable drift. |

Bind structural validation, hash, sections, symbols and probe reads to one
immutable bounded object snapshot. Restrict and validate actual TOC names and
structure rather than skipping arbitrary reserved prefixes. Bind each actual
tool executable's expected bytes and stable identity consistently with its ELF
facts, checking before/after execution. The original author owns these changes
in a new isolated worktree; this reviewer edits no implementation.

The archive parser's existing `#1/-1` name extent also reaches `read(-1)` before
its length rejection; the strict TOC/member-bound fix should reject negative or
non-digit extents before reading. This observation is within P2-2's parser fix
scope; no large allocation was attempted and it is not counted as another
reproduced finding.

Actual reproducible commands are recorded in `evidence-fail1.json` under
registered PLATCOMP-001. Both probes completed exit 0 because they successfully
reproduced the failures; the review outcome is fail. The first child peaked at
45834240 bytes and the second at 45432832 bytes, with stable three-sample
4 GiB admission and empty owned-process lists afterward. No compiler, archiver,
loader, source matrix, guest or original input was executed/mutated. Genuine
historical objects are used only as negative controls, never as new guest proof.
All generated object/archive/tool-copy bytes stay in ignored owned runs/.

Root, kernel integrator and the original author received these findings early.
The earlier 5152 source, 7d6cd9 capsule and original worktree remain frozen.
Independent regressions must run on the exact isolated correction before any
VM-036 acceptance. VM-038's accepted qualifier and VM-039 consumer work can
continue independently.
