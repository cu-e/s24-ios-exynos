# AVFHOST-001: real pinned shim to owned synthetic payload

Date: 2026-11-05. Owner: codex-team-avf-handoff-20261105-bd. Task: VM-005.

This experiment executes the genuine AVF shim and an explicitly owned synthetic
arm64 Mach-O fixture. It does not execute an XNU kernel, PID 1, iOS, Linux or any
phone. Inherited shim text naming XNU describes its upstream purpose, not the
identity of the synthetic fixture.

Read-only inputs:

- Scion donor `a6f4bc38aa244359cd365c976244a88c9d6b3304`, reviewed AVF loader,
  start, UART, FDT, payload and device-tree code. Existing unmodified Image is
  35,368 bytes, SHA256
  `283f6740424011959ebe03e71ce910a81bbfa3b7ba31c6395ab6f8aab77eaf87`.
- Qualified QEMU 10.2.0 source commit
  `698104725efad4b29079d857dfdebbd804e34c99`; existing built binary SHA256
  `bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11`.
- Existing compiler and source-built ld64 only; no SDK, Apple binary or new
  dependency acquisition, no shared reference or VM-002 file/artifact edits.

Derivation before execution:

1. QEMU `hw/arm/virt.c` places virtual RAM at `0x40000000`, PL011 at
   `0x09000000`, GICv3 distributor/redistributor at `0x08000000`/`0x080a0000`,
   and uses HVC PSCI when virtualization is off. These are virtual devices.
2. QEMU `hw/arm/boot.c` honors arm64 Image offset 0 and moves such an Image
   2 MiB above RAM to avoid its own bootloader. Its real boot stub supplies
   the generated FDT in x0. The genuine PIE shim must relocate and execute at
   that actual address; no load-address patch or bypass is allowed.
3. The shim requires segment VM addresses >= `0xfffffff007000000` and a
   nonzero LC_UNIXTHREAD entry. Its physical slide is
   `physBase - 0xfffffff004000000`, placing this fixture >= `0x43000000`.
   A 256 MiB virtual machine provides a 224 MiB XNU-style window after the
   panic region/alignment reservation. This meets its 48 MiB code placement,
   DT/bootargs allocation and 64 MiB spare check; 128 MiB would not. No RAM
   larger than the authorized 512 MiB initial ceiling is required.
4. Check actual generated QEMU DTB independently, including RAM, UART, GICv3,
   PSCI and initrd addresses. Compile/link an actual freestanding arm64 Mach-O
   with no libc/SDK, no absolute runtime data pointers and no low PAGEZERO
   segment. Derive the physical entry and bootargs addresses from its real
   segments and loader rules.
5. The guest fixture must check its entry context, bootargs revision/layout,
   physical/virtual memory values, command-line cookie and bounds, translated
   Apple device-tree properties and its HVC PSCI method. Only then print an
   explicitly SYNTHETIC pass marker and call PSCI SYSTEM_OFF. Capture the real
   shim and fixture serial output plus natural QEMU exit.
6. Independent negative controls: corrupt Mach-O magic for a real shim rejection;
   wrong command cookie for a real guest assertion rejection; a separately
   compiled fixture that spins instead of PSCI stop for an actual bounded
   QEMU termination control. Never synthesize console output on the host.

Resources: one small compiler/linker job at a time, <=256 MiB sampled total RSS;
one 256 MiB QEMU fixture at a time, <=512 MiB sampled total RSS. Each QEMU command
has a <=10 second deadline plus owned-session cleanup, with no unrelated process
signals. No heavy build lease is used. Record actual commands, exits, hashes,
CPU console, source/DTB/Mach-O contract, resource samples, every failure and a
handoff. Genuine incompatibility is a retained blocker, never a synthetic pass.
