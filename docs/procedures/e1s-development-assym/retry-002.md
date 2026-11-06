# STR013ASSYM-002: supply the genuine mandatory sanitizer input

Preserve failed generate-1 and its source plan. Reuse the accepted normal
unsupported compiler-feature receipt (BOUND_CHECKS=0); do not probe again.
The absent UBSan ignorelist was a missed preflight input in the first plan.

Prepare a fresh generate-2 plan. Read native san/memory/Makefile lines38–41:
the original sed concatenates kasan-blacklist, ubsan-blacklist and
kasan-blacklist-arm64 in that order, resolving only source path prefixes.
Run the original source validator against the new generated ignorelist before
compilation. No sanitizer flag or entry may be removed. MakeInc.def's existing
UBSAN_BLACKLIST variable binds this owned generated input; a fresh read-only
query must prove the only compile changes are that pathname and fresh output
and MD operands. Preserve original flags and source/header contexts.

Preflight every current path operand: compiler/source/forced include, all
search directories (including explicit absence), ignorelist producer, output,
MD and any explicit resource directory. There is no explicit resource-dir in
this -nostdinc vector; do not add one speculatively. Check actual new MD after
the root-admitted serial generation, validation, one -S compile and original
offset-extraction sed. Use existing bounded runner,2GiB/120s child/300s whole.
No generation or compiler runs during preparation; no native runtime claim.
