# ROOT101 Python safe-path source correction

ROOT99 attempted the previously accepted controller0795. It exited1 in Python
argparse/_colorize/dataclasses import setup: the controller's fixture directory
was automatically prepended to sys.path, so import inspect selected the sibling
project inspector instead of the standard library. The local inspector imports
dataclass, yielding a circular partially initialized dataclasses ImportError.

Preserve MAIN artifacts/team-coordination/20261106-team/loader99/{launch.py,
launched.json,receipt.json,stderr.txt,stdout.txt}, old root97-approval.json and
all prior source freezes. Root99 receipt records no measurement evidence and no
owned survivors; root released the lease. No controls, ordinary builder, target
compiler or inspector stage started and no owned001 output namespace exists.
STR031BUILD-001 remains PLANNED, rather than an actual failed control experiment.

The minimal isolation change is controller Python -P plus a frozen child
environment PYTHONSAFEPATH=1. The installed Python3.14 manual documents these as
suppressing the potentially unsafe script-directory/current-directory prepend.
The controller asserts sys.flags.safe_path before constructing ArgumentParser.
The root invokes it with an explicit environment excluding PYTHONPATH and user
site, and the existing child environment is cleared/rebuilt with the safe-path
setting preserved. No historical inspect.py is renamed or removed. All23
recorded target-builder argv and all compiler/linker/native flags stay unchanged;
PYTHONSAFEPATH propagates through unchanged e1s.run to Python packagers too.

Source import audit: source-controls.py and inspect.py import only standard
modules directly. Source-controls loads the candidate builder from its exact
bound file. Builder deliberately inserts its bound WT/tools directory and imports
the pinned sources.py, which itself has only standard imports. This explicit
source-verifier path remains available under -P. Neither donor fix_image.py nor
mkboot.py requires adjacent modules; all their imports are standard. The three
qualified helpers are loaded from captured, SHA-checked explicit paths and have
standard-library top-level imports. No implicit fixture sibling import is needed.
This is source reasoning; no corrected Python launch/control test ran here.

The new plan is prepare-003, derived from immutable plan1df with safe child env,
new inspector plan pointer and additive source-provenance bindings. Its23 target
vectors, source bodies, snapshot inspector, stages, ordinary builder001 and
source-controls001/inspection001 outputs remain unchanged and absent. New
controller is additive run-root101.py; measurement measure-root101-001; exact
lease e1s-loader-log-builder-20261106-101; fresh approval root101-approval.json.
Old callers/approvals remain immutable. Root alone reserves/releases the heavy
lease and independently checks actual exit0, passing evidence and zero survivors.
Existing600second work/690second external/2GiB combined RSS guards remain.

No actual control/compiler/inspector rerun is authorized to the source author.
Independent source review and separate fresh root approval precede execution.
Kernel0011/12 ownership, phone/native execution, mappings, persistence, retrieval
and recovery remain unqualified; the unchanged probe's physical assumptions are
also unqualified. No full Python standard-library/runtime closure is asserted.
