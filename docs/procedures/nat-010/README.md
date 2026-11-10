# NAT-010 loader entry and coherency, 2026-11-10

Host source review, ARM build and independent image verification only.

The NAT-006 assembly uses a PC-relative stack, BSS and DTB before clearing M.
No S-Boot translation-table or identity-mapping witness was supplied. Disabling
M at an unknown VA cannot be justified by cleaning the loader's data: the next
instruction, stack or vector could resolve to a different physical address.
Therefore the hardened entry **rejects M=1 or C=1 before stack or C access**.
It does not attempt an unsafe live translation transition. This also applies
after the EL2-to-EL1 path. EL2's own entry mapping remains subject to the upstream
boot protocol and is not qualified here.

This is an enforced admission condition, not a measurement of S-Boot's SCTLR.
Linux's arm64 boot protocol requires MMU off and the loaded image cleaned to PoC:
https://docs.kernel.org/arch/arm64/booting.html ("Before jumping into the kernel").
The original loader was entered as a Linux Image. That contract is not proof
that the particular bootloader complies. A future native measurement can record
SCTLR; M/C enabled produces a deliberate early halt, not a high-DRAM write.

`patch.py` consumes the preserved NAT-006 build-002 source. `loader.patch`
contains the resulting assembly/C changes. The final C path cleans the entire
selected window after every segment/ADT/boot_args write, including zero-only
pages, before the hold and return. With this runtime DTB the range is
[0x9de400000,0x9fe400000), exactly 512 MiB, excluding EL2 reserved memory.
`clean` derives line size from CTR_EL0, executes dc civac per line and dsb sy.
The assembly then cleans the loader through _end (including both stacks and
boot_args_pa), executes dsb sy, loads boot_args, and disables M/C/I with an ISB.
There are no stores after that final loader clean; the clean loop uses registers.
Code changes are followed by the existing ic iallu / dsb / isb sequence.

Validation: actual ARM assembly and all five C objects compile; zero C
R_AARCH64_ABS relocations. The independent NAT-006 verifier checks the rebuilt
96 MiB RECOVERY image, stock sections, payload segments, ADT, stock restore and
three runtime-FDT window/framebuffer scenarios. These do not simulate cache
hardware or prove bootability. Build failure on the first logical-immediate
encoding was retained; ARM's non-contiguous #5 mask was replaced with two tbnz.

Reproduction from repository root:

```
# Use a new output name; preserve previous attempts.
# Copy artifacts/nat-006/build-002/source into OUTPUT/source first.
python3 docs/procedures/nat-010/patch.py OUTPUT/source
python3 docs/procedures/nat-010/build.py OUTPUT
```

The build script consumes the exact saved NAT-006 payload and pinned inputs;
its commands.json and verifier report capture commands, exit codes and checks.
Native entry, actual cache behavior and Android recovery remain unmeasured.
