# Native E1S source-port preservation

STR014 original owner codex-e1s-native-source-ports-20261106-sr14. Independent
worktree from current MAIN b993ad9678ed3c77713087f62dafb5d40e36ceec. CM native
body-plan c24ec64f and inputs7024f0ea were read and physically hashed. This is
source preparation only: no compiler, generator, linker, Make query or target
execution. Existing tools/sources.py supplies the Git helper; no executor,
controller, shared helper or test matrix is added.

The accepted STR004 source is its original5111-file manifest f884bf7f/profile
8ef30b4a. All5111 source bytes match before preparation; its18 extra files are
only Git metadata. Preserve that whole original tree/Git and all configurations.
Create a fresh owned source from exactly the manifest-listed files. The derived
tree must have its own isolated Git root: reuse sources.git(work,'init','--quiet')
as prepare_xnu.py documents, and verify rev-parse --show-toplevel before apply.
Parent-project Git discovery may skip paths and return0, so exit0 is insufficient.

E1SNATIVEPORTS-001 will perform check then apply for three exact existing patches:
7426580b (cache alias/platform guards), promoted unchanged7c6e8ad0 (existing
kernel printf declaration), promoted unchanged164dbcc1 (genuine proc_pid
prototype). Preserve their original locations, producer fixtures and attribution.
The expected source paths/pre/post hashes and exact patch/input identities are
in fixtures/public/e1s-native-source-ports/inputs.json. No guessed edits,
stubs, export deletion or declarations beyond those accepted bytes are allowed.

After source-only application require exact accepted postimages for
osfmk/arm64/caches_asm.s, osfmk/arm64/start.s, osfmk/arm/model_dep.c,
pexpert/arm/pe_init.c, osfmk/minicrypto/mc_provider.c and
osfmk/arm64/user_exception_trace.c. Full before/after manifests must prove all
other5105 files identical. In particular headers, Make/config source and generator
inputs stay byte-identical, allowing downstream consumers to assess the new
source context without modifying accepted configuration/source producers.

Actual prepared sources/manifests are owned under artifacts/e1s-native-source-ports/derive-001.
Register the source-only experiment before copy/check/apply; the180second plan
contains no compiler or target command. Freeze actual argv/exitcodes, six-file
proof, unchanged-file proof and source-context descriptor after real application.
Preserve failure if one occurs. Rehash all original inputs after completion.

A consumer must explicitly select the derived root and the genuine DEVELOPMENT
recipes/generated context. Accepted generated Makefiles still name their original
source paths and are not rewritten here. Neither existing RELEASE objects nor
old source-port compile success receives new DEVELOPMENT qualification. Compile
these six real source bodies only during a separate genuine DEVELOPMENT body
build. The37 export ABI requirements and native hardware/runtime remain open.
Independent review/publication/common/root acceptance precede SR14 closure.

E1SNATIVEPORTS-001 actually applied the three patches once. All10 Git operations
exited0 through existing sources.git; isolated toplevel was verified for each
patch. Six postimages exactly match the accepted prior-port hashes and all5105
other files match the base manifest. Original5111 source files, original18 Git
metadata files and all bound inputs remain byte-identical. Full derived source
and both manifests/proof are in derive-001; source-context.json binds the usable
root and expected consumer boundary. Actual elapsed5.458seconds; no compiler,
generator, linker, Make query, target execution or object reuse occurred.

The conventional evidence preserves raw4ea05b1b/proof821eb152/derivedmanifest
f85b6990 and all ten actual argv/exitcodes. Existing sources.git exposes stdout
on success but not its captured stderr; raw empty-stderr fields were unobserved
placeholders, not measured-empty output. Raw getrusage high-water is retained
without claiming process-sampled or aggregate RSS/budget qualification.
No actual result is rerun or altered to change those observation limits.

Independent source/context review and publication/common/root acceptance are
next. The original SR14 claim remains open until explicit root acceptance.
