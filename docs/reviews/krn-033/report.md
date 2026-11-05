# Independent review of KRN-033

**No concrete P0/P1/P2 finding** in the frozen bounded GCM adapter. Reviewed
series `245299afcaab8e995c04a2e86b50d793e9102453`,
`f845dc66ff0124bcdbfe36965c95ce18c3da7c8c`,
`d8a9fd106edaa4d3140503237ba6dd99db92b33f`.
This conclusion applies to the stated fixed software profile and the selected
public XNU declarations, not full provider or native compatibility.

Genuine type/storage/caller assessment:

* Actual selected `ccmode_impl.h`, `ccmode.h`, `cc.h` and registration typedefs
  match XNU `c54f35ca767986246321eb901baf8f5ff7923f6a`. The typed witness assigns
  both managed helpers without function-pointer casts. `gcm.c` builds the real
  descriptor with its six callbacks and direction/custom identity checks.
* Independent reading of the actual ARM object layout symbol yields
  **1312/16** owned bytes/alignment, GCM624/block296/AES288, descriptor80. Fresh
  host compilation agrees. The selected corecrypto forwarding wrappers obtain
  `gcm->size` dynamically, and ESP's schedule reserves both rounded sizes plus
  its alignment allowance. The context is not required to fit a fixed2048-byte
  production slot;2048 is the worker suite's allocation convenience.
* All26 vendored/shared source members match the full pinned official Mbed
  archive, with the exact shared include-only `common.h` transformation
  independently reconstructed. Complete GCM44572 and check_config48196 bytes
  are used. Apache component notices/license are preserved; the default full
  configuration is not the selected profile. The fixed profile excludes heap/
  generic-cipher/PSA/ALT/ISA paths. Seed and active AES/GCM state are inline,
  with schedule offsets rather than borrowed foreign pointers. The actual
  linked objects contain exactly one AES-ECB and one shared zeroizer definition.

Lifecycle/nonce/authentication assessment:

* `gcm.c` load/initialize binds a context to its address and validates its fixed
  backend state. Key and IV material are consumed into owned schedules/state.
  Live managed reinitialization, wrong helper direction/descriptor, copied
  context use and manual-IV/managed-IV mixing are rejected. Clearing is an
  explicit destruction/reconstruction boundary. It cannot provide uniqueness
  after external memory rollback/reconstruction, across other contexts, or
  persistently across restarts; these limits are stated in the implementation.
* Reset retains key and managed salt/counter, including exhaustion. Increment
  uses exactly the final8 bytes in big-endian order, retains salt4, and commits
  only after output/mode validation and successful start. Carry/exhaustion and
  repeated resets do not roll the counter back or silently refill authority.
* WAIT_IV/AAD/DATA/FINAL admission, text/AAD bounds, zero operations, wrapping
  extents, context aliases and partial input/output overlap are checked before
  normal rejected-operation state/output changes. Updates emit each partial
  byte immediately; exact in-place operation is supported. Unexpected backend
  update failure is explicitly separated from ordinary admission rejection.
* Decrypt finalization copies the supplied expected tag before comparison,
  uses the genuine constant-time helper, overwrites the tag with the computed
  value on both success and mismatch, and consumes the message on mismatch.
  Streamed plaintext remains provisional. Tags4..16 are the stated bounded
  policy; this is not an inference about unspecified private implementations.

Independent measurements:

* Rehashed155 unique original capsule artifacts and checked actual frozen
  source bytes against the exact implementation commit. Reconstructed the
  primary selector independently from all47250 NIST records:3150 parameter
  groups and4723 first-valid/first-FAIL representatives, plus45 recorded EVP
  extras. Every selected primary input/tag and valid plaintext agrees with the
  original corpus. FAIL plaintext/computed tags remain explicitly oracle-derived.
* Parsed real XNUP framing and compared embedded Mach-O bytes. Positive and
  wrong-cookie kernels equal the actual normal image; the corrupt control
  changes exactly one expected-ciphertext byte at297016; spin carries the real
  spin image. Actual positive console count0x18bf0d2 equals25948370, with verified
  synthetic handoff and PSCI exit. The three control consoles, real3-second
  timeout, stable admission samples and zero surviving children agree with
  actual command capsules. No guest was run by this review.
* The host and ARM use the same unchanged suite/corpus; existing host and ARM
  object/dependency hashes bind it. Earlier host/CPU memory-deferred reports
  retain failed outcomes. The only allowed earlier CPU driver repair is exactly
  the recorded summary insertion; the original report remains present and its
  commands/results match. These facts support actual synthetic ARM execution,
  not XNU or Exynos execution.
* A fresh, separately authored ASan/UBSan probe passed **1499 checks** after
  linking six hash-verified existing adapter/backend/shared objects. It used
  the actual descriptor-sized context with16-byte guards on either side and
  tested NIST AES-GCM bytes, immediate split/in-place output, mismatch/tag
  overwrite, provisional plaintext, invalid-tag/alias/phase snapshots, external
  key/IV mutations, copied contexts, managed salt/carry/reset/exhaustion, and
  live reconstruction/mixing gates. Both compile and run had three prospective
  >=4GiB samples one second apart. Exactly one tiny compiler job ran; observed
  compiler-tree RSS peaked at132526080 bytes, below256MiB. The20ms sampling of
  the very short probe is not presented as its exact peak. Reviewer VmHWM was
 21772KiB, not an inherited `ru_maxrss` value. No descendants remain.

An initial independent parser failed on an empty AAD field, then was corrected.
The next run completed source/corpus verification and deferred before launching
a compiler below the4GiB floor. That report is retained. The final continuation
rechecked its identities and ran only the missing focused probe and byte controls;
it did not repeat the full algorithm matrix or any QEMU execution.

Software AES tables are not side-channel qualified. This review provides no
provider registration, full kernel link, full crypto provider, private Apple
ABI, FIPS, protocol-global nonce guarantee, XNU execution or native-device result.
The review-only task remains in progress for coordinator acceptance/common
integration checks. Evidence and reproduction details are in handoff.md and
qualified-evidence.json.
