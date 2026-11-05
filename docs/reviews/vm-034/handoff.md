# REV-026: source-built owned PID1 compiled ABI review

Owner codex-review-pid1-20261106-ds. Scope docs/reviews/vm-034 only. Original
VM-008 is done and unchanged. No producer/source mutation, compiler/linker,
QEMU/guest, whole common check, device or MAIN implementation write occurred.
Read-only Git blob queries use GIT_NO_LAZY_FETCH=1 and GIT_OPTIONAL_LOCKS=0.

The exact VM-034 candidate passes this independent compiled-source/ARM64/static
Mach-O assessment. No actionable P0/P1/P2 finding was identified within that scope.
This does not establish real PID1, kernel syscall execution, initial stack mapping,
console operation, code-signing/exec policy, kernel panic/PSCI or bounded VM stop.
It is eligible for VM-025's separate candidate-list preflight and VM-024's separate
raw mockfs packaging checks under their own task authority.

## Exact immutable candidate

- Source commits: 0a60389, docs/build commit60afd5dab564ee74c2062064c99c7da5e12b96f7,
  final export docs2b278bfad93de50f084a34e7c8f5983bea988eb1. Independent Git blob
  reads prove source and producer bytes agree across all three.
- Raw five-command build capsule:
  worktrees/vm-034-20261106/artifacts/avf-guest-pid1-build/build-1/evidence.json,
  SHA25601488b5be195fe61a0e0880c60b51190a7cb38c33dd0ba7af3d68ac22bc266b2.
- Image: same directory/pid1, SHA256
  fac53e7a7799b06e9ced2ef944d079803c49ebbdd60a5f294f92bdd0726775f3.
- Four-field candidate.json in that directory, SHA256
  0bdfc24445a1a213790546a79a62975691c9ff334cd6bedb6f954859cf41f63e.
  reviewed-candidate.json here is a byte-identical metadata copy; original image
  and descriptor paths are unchanged.
- Owned source SHA256
  68de57b2e27480f39cabdcf1372176ddbf8e275b9c5309c2ac529c6e0be01190.
- Original mockfs-provenance.json SHA256
  28ea3ec9dab6cc84b0dbd024271e6b41413e69e62f060830ee0426a6ff2c0b25.
  Its acyclic raw-evidence/candidate/provenance handoff index hashes all match.

## Source and machine evidence

Selected source is the immutable VM-008 public XNU/Scion guest preparation:
XNU c54f35ca767986246321eb901baf8f5ff7923f6a, Scion
 a6f4bc38aa244359cd365c976244a88c9d6b3304. Additional named source checks remain
bound to the frozen prepared-source hash map. Existing source-built Clang17,
ld64/nm and their source provenance match recorded tool bytes; no SDK was used.
The actual five commands equal the recorded recipes, source-plan canonical argv
changes only the owned output location, root approval matches, each admitted
three >=4GiB samples >=1s apart, and all children retired. Empty nm -u stdout
is corroborated by independently decoding symbol tables, not merely trusted.

Selected syscalls.master defines exit1/write4/open5/getpid20/sysctlbyname274.
proc_reg.h1941 names x16; mach/arm/vm_param.h361 and libsyscall/custom/SYS.h453
bind SVC#0x80. bsd/dev/arm/systemcalls.c455-483 copies direct arguments from
saved x0 upward;586-623 overwrites x0 AND x1 and sets carry on errors.
arm_clear_u64_syscall_error659 clears carry before dispatch. locore.s1038-1055
restores x2..x15 from the saved state, supporting live pointer/count/fd registers.
The replacement declares x0/x1/x16 read-write, a nonaliasing early-clobber carry
result, memory and cc. LLVM's six opaque asm records retain those outputs and
clobbers. The actual legacy input-only-x1 source is rejected; its old build is
not promoted by structural similarity.

All six real SVC words are0xd4001001, immediately followed by CSET HS into a
register outside x0..x5/x16. Actual x16 literals occur in order5,20,274,4,4,1.
The sysctl name length is11; kern_newsysctl.c1958-2009 copies exactly that length,
adds its own NUL and reads the LP64 old-length pointer. The IR reloads returned
length/content after the memory-clobber syscall. The success edge requires
console success/nonnegative fd, no getpid error with returned pid==1, no sysctl
error, length7 and actual returned Darwin+NUL bytes. This is a conditional owned
marker; no kernel-version banner or forced identity result is emitted.

Both optimized write loops reload x1 from live x10 after every clobbering SVC;
fd persists in x8 and remaining count in x2. Machine CMP/CCMP rejects carry errors,
nonpositive returns and values greater than remaining count. ADD advances x10,
SUB decreases x2, HS backedge leads through a zero-count exit. Successful partial
writes therefore make finite positive progress (43/37 message bytes). Blocking
inside a kernel syscall remains a runtime/host-deadline issue, not a proven stop.
Exit uses the actual syscall then a user-safe YIELD loop if it unexpectedly returns.
The selected initproc exit/panic behavior is not exercised by this review.

The real object and executable have504 bytes of code,126 ARM64 words. Exactly
eight instruction locations change at link, corresponding to the eight genuine
PAGE21/PAGEOFF12 object relocations. Their ADR+NOP relaxations resolve to actual
/dev/console, kern.ostype and both owned message literals. SVC, carry and loop
instructions are otherwise unchanged. There is no hidden libc/memset/cerror import;
LLVM's memset intrinsic lowered to inline zero stores.

The executable is16512 bytes, ARM64_ALL MH_EXECUTE/MH_NOUNDEFS, no dyld/import/
undefined symbol or linked relocation. It has PAGEZERO0..4GiB (no file bytes),
16KiB RX TEXT at0x100000000 and read-only LINKEDIT. FourGiB pagezero is virtual
reservation, not a4GiB physical RAM requirement. LC_UNIXTHREAD flavor6/count68
contains PC0x100003d9c at _start/__text, zero other initial registers/SP/CPSR.
Selected mach_loader.c509-515 and640-648 impose ARM64's16KiB map and hard4GiB
pagezero; status.c1807-1872 provides the default-stack route for zero state.
Actual mapping, signing/exec and initial thread behavior remain unexecuted. This
image has no build/min-version/code-signature load command; no runtime policy
admission is inferred from static byte layout.

## Controls and retained review attempts

runs/review-4/report.json passes70 positive binding/provenance checks and31
source/IR/machine/image mutation controls. These include actual legacy x1 failure,
missing clobbers/early output, wrong syscall/forced identity/zero progress,
wrong SVC/carry, destroyed pointer/count/backedge, arm64e/ELF/wrong CPU/dynamic
flags, malformed load commands/thread/entry/pagezero/perms/import and truncation.
Equivalent source formatting remains accepted, so rejection is not just a fixed
source hash. The independent parser is deliberately candidate-specific, not a
universal Mach-O loader or runtime emulator.

First reviewer attempts are preserved. review-1 incorrectly assumed the first
string-table byte must be NUL; actual cctools uses a reserved leading space+NUL.
review-2 incorrectly required the empty undefined range's starting index to be0;
actual LC_DYSYMTAB legally uses end-of-symbols with count0. Those are reviewer
oracle corrections, not producer findings. review-3 passed62 bindings/31 controls;
review-4 adds exact recipe/source-plan/approval/admission/handoff checks (70 total).
No compiler, linker, QEMU or common check was rerun. Current-image reviewer peak
27,439,104 bytes; all read-only Git commands exited0 under finite timeouts.

Next: exact candidate to VM-025 owner guest_exec_13 and original mockfs provenance
+same image to VM-024 owner guest_exec_12. Original dr still owns VM-034; this
review does not complete it or alter blocked VM-002/KRN-036 evidence. Root and
INT-002 lab_worker decide integration/whole-common acceptance. REV-026 stays
in_progress until original-reviewer completion is explicitly accepted.
