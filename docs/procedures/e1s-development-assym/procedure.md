# Native DEVELOPMENT ARM64 E1S assembly offsets

STR013ASSYM-001 derives the actual native osfmk genassym rule from accepted
STR009 configurations and STR011 raw exports. The original STR004 source is
retained: STR014 changes six unrelated body files; genassym and its structure
headers are unchanged. No old RELEASE or BCM offsets are adopted.

Preparation performs two read-only GNU Make queries with explicit BOUND_CHECKS
0 and 1, preventing the Makefile's parse-time compiler probe. Both vectors are
preserved. A separately root-admitted native compiler capability probe selects
the matching vector exactly as MakeInc.def specifies; no target compiler runs
during preparation. A missing or invalid probe result stops execution.

The admitted sequence is the genuine `CC -E -fbounds-attributes /dev/null`
probe, one selected `GENASSYM_KCC CFLAGS CFLAGS_NOLTO_FLAG
-fno-integrated-as -MD -S` invocation, and the original DEFINITION__define__
sed extraction. The compiler output named genassym.o is assembly text, never a
target executable. Preserve all failures, actual command evidence, RSS and
cleanup. Use the existing root bounded runner, one serial job, 120 seconds per
compiler, 300 seconds whole and at most 2 GiB owned RSS. No link or guest run.

The fresh compile directory receives exact accepted osfmk configuration copies
so the genuine `-I.` resolves native DEVELOPMENT configuration. Original raw
exports retain their accepted paths. The separately qualified public
TargetConditionals include root is appended without SDK authority. Original
include order is otherwise unchanged. No MIG/syscall/version directory is
required merely because an old helper added it. Fresh actual MD decides the
complete prerequisite closure; old RELEASE364 MD is reference only.

After execution validate actual source/config/raw/public-header dependencies,
compiler/source/profile pins, native 10 CPU / 4 cluster geometry and selected
MACH_ASSERT/PPL flags. Extracted definitions must have unique names, original
numeric companions and exact source sed bytes. Deliver the generated assym.s
directory for native start.s, plus assembly/MD and their measured hashes.
Generation alone grants no full kernel, hardware or ABI qualification.
