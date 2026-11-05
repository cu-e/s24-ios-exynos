# KRN-029 planned interfaces and experiment

Owned scope: two typed `ccmode_xts` descriptors, no provider registration.
Actual selected XNU headers at c54f35ca767986246321eb901baf8f5ff7923f6a
supply every descriptor and opaque context declaration. Caller creates descriptors
with `s24_xts_descriptor(mode, decrypt)` before publishing them and keeps them
immutable for all users. Backend is real Mbed TLS AES at
068ff080b369adfac81509f9b57b2afabaf82dc5, Apache-2.0 choice, regular software
ROM-table profile, without ALT, assembly, acceleration, PSA, entropy or allocation.
Key context owns copied schedules. Callback const input is copied to a genuine
mutable temporary AES context and cleared. Two separate keys are16/32 bytes EACH.
Tweak owns encrypted raw16-byte IV, key identity and cumulative full-block progress.
Maximum unit is2^20 blocks; zero blocks succeed without touching input/output.
Disjoint/in-place operation is admitted, partial overlap and integer extent overflow
are rejected before writes. Serialized context access/lifetime and accessible
buffer capacity remain caller duties. Reinitializing a key invalidates its old
tweak. Invalid initialization clears the context; void key_sched expands real keys
and leaves invalid state on error. No partial-byte ciphertext stealing is exposed.

Owned runtime.h is a synthetic QEMU virt runtime derived from accepted VM-005,
not an SDK or XNU. Existing shim and QEMU bytes/source pins stay unchanged. It
checks entry/bootargs/DT/cookie and reports actual adapter vector results, then
PSCI powers off the virtual guest. Wrong-cookie, corrupted expected vector and
timeout controls must not produce PASS and must leave no live owned descendants.

Before any verification run register XTS-001. Obtain and hash NIST primary XTS
vectors; select full-block raw-tweak records with explicit exclusions. Compare
actual host adapter against those records and independently installed OpenSSL EVP
XTS for deterministic extra inputs. Run host ASan+UBSan, input/state/overflow/
split/in-place/error/zeroization cases and real sanitizer negative controls.
Compile actual adapter+same vectors into ARM64 MachO with genuine selected
headers; measure context size/alignment and execute through unchanged AVF/QEMU.
One sequential compiler job <=256MiB RSS; one guest RAM256MiB, total owned
RSS<=512MiB; bounded process-session monitoring and cleanup. ASan execution
must not receive an address-space limit, since shadow reservation is virtual.
Save commands, exits, timestamps, actual compiler/resource/runtime/input hashes,
commit, samples and artifact hashes. Failures stay recorded. No physical device,
full provider/XNU, Apple-private ABI, FIPS or side-channel assurance is claimed.
The existing XNU wrapper ignores xts pointer errors; direct descriptor testing
cannot qualify its error propagation.
