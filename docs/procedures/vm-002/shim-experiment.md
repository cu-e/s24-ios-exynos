# VMHOST-002: source-only AVF shim with placeholder identity

Date: 2026-11-05. Owner: codex-team-vm-20261105-am. Task: VM-002.

The installed Android NDK LLVM directory has existing `ld.lld`, `llvm-objcopy`
and `llvm-readelf` beside the resolved Clang executable. No tool acquisition is
needed for this small shim. Plan before execution:

1. Extract only the ten named shim source/header/linker files, the reviewed
   `xnuloader/mkidentity.py`, and component license text from the selected full
   donor commit into a new task-local artifact directory. Hash every input.
2. Run only the reviewed Python generator's `--placeholder` path. This emits
   four empty property tables and reads no IPSW, firmware or Apple data.
3. Compile `start.S`, `avfboot.c`, `fdtx.c`, `uart.c`, `pci.c` sequentially with
   the pinned donor build flags; link with the reviewed linker script. Use the
   already installed LLVM tools, 512 MiB address-space limit and a 30-second
   deadline per subprocess. Record the tools' actual paths and hashes.
4. Inspect actual ELF relocation output. Reject any AArch64 dynamic relocation
   other than `R_AARCH64_RELATIVE`, matching the shim's start-code constraint.
   Produce an arm64 Image using the existing objcopy and check its header magic.
5. Supply this built shim and the owned PID 1 to the host harness. Record the
   remaining missing inputs. No kernel build, emulator launch, source setup
   script, binary download, SDK acquisition, phone access or global install.

A successfully linked shim is source-build evidence. It neither executes XNU
nor establishes that the selected kernel/board configuration is VM-compatible.
