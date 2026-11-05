# Genuine compiler-rt cc_kext correction

Base: LLVM17.0.6 commit 6009708b4367171ccdbf4b5905cb6a803753fe18,
Apache-2.0 WITH LLVM-exception; original notices remain in copied source.
source-pin.json binds the exact original/patched ashrti3.c and patch bytes.

CCKEXT-014's actual full ASan+UBSan run diagnoses a negative signed left shift
at original ashrti3.c:34. int_lib.h documents two's complement and arithmetic
signed right shift, but not a defining contract for this signed left shift.
The one-line correction converts the high word to du_int before shifting it
into the low word. Unsigned modulo conversion preserves that word's bit pattern;
the branch bounds the shift to1..63. Signature, target ABI, arithmetic signed
right shift and every selected runtime function remain unchanged.

Recompile only this native translation unit with its recorded native command,
reuse the other286 immutable actual objects, then rebuild the genuine archive.
The original failing source is an executed UBSan negative control. The corrected
source must pass full ASan+UBSan generic integer checks and boundary/random
arithmetic-shift tests against an unsigned64-bit-limb oracle. No sanitizer
category is disabled to create a successful result.
