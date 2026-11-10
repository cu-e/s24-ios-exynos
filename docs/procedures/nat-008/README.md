# NAT-008 host provisioning and restore package, 2026-11-10

Host-only preparation; no USB device was opened, reset or written.

Tool: open-source Llucs/odin4 (not Samsung's proprietary executable), revision
338fde4569ee3b0743098714199361835f96015b, Apache-2.0 with bundled component
notices retained in `references/odin4-nat008/{LICENSE,NOTICE,lib}`.
Primary source: https://github.com/Llucs/odin4/tree/338fde4569ee3b0743098714199361835f96015b
Binary: `artifacts/nat-008/odin4`; `-v` reports `7.3.0-a46321b`.
The reported version suffix is an upstream literal, not the actual checkout SHA.
Exact binary, dependency and package hashes are in evidence.json.

Fedora dependencies were downloaded with `dnf download --resolve` and extracted
with rpm2cpio/cpio into artifacts/nat-008/prefix, without system installation.
The first sudo install attempt required a password; local provisioning needed none.
Fedora names the Crypto++ pkgconfig module libcryptopp; a local libcrypto++ alias
was provided for upstream CMake. CMake built the unmodified static core and 47
passing upstream tests. The CLI was linked dynamically with g++ because upstream
requests static libstdc++, which this host lacks. No runtime/source patches.
Exact successful link: `g++ -std=c++23 -O2 -I references/odin4-nat008/include
references/odin4-nat008/src/cli/main.cpp artifacts/nat-008/build/libodin4_static.a
artifacts/nat-008/build/liblz4_lib.a -L "$PWD/artifacts/nat-008/prefix/usr/lib64"
-Wl,-rpath,"$PWD/artifacts/nat-008/prefix/usr/lib64" -lcryptopp
-l:libusb-1.0.so.0 -o artifacts/nat-008/odin4`.

`src/odin4.cpp:150-230` opens USB and starts a session even with --check-only.
That flag is therefore unsuitable for offline verification. The local offline.cpp
harness calls the unmodified `process_tar_file` with do_flash=false, unknown
entries forbidden, and an unopened USB object. Its PIT fixture has one RECOVERY
entry: it tests archive-name mapping, not this device's real PIT or protocol.
The real tar passes; invalid checksum, truncation and unexpected partition tests
must reject. Independent Python checks require exactly one regular recovery.img,
96 MiB, byte-identical to the NAT-001 stock hash
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
The tar hash is 2787aa3e07d1f09d5f2c808166e0640719f111a618105ceed1ef67ea721fe84e.

## Candidate NAT-004 restore sequence (documentation only)

This sequence replaces RECOVERY with its exact saved stock bytes; it is a
partition write, not a proven non-destructive operation. Host validation cannot
establish Download Mode compatibility or preservation after a failed transfer.
NAT-004 must first qualify physical Download Mode access and the actual PIT,
confirm a single RECOVERY mapping and its 96 MiB capacity, and have a separate
authorized hardware recovery plan. No such hardware qualification occurred here.

1. Validate hashes and the archive offline using check.py.
2. Enter Download Mode using the separately qualified physical procedure.
3. Identify the exact device path using `artifacts/nat-008/odin4 -l`.
4. Upstream also checks the model in archive filenames. Copy the verified tar
   to `artifacts/nat-008/SM-S921B_recovery-stock-odin.tar` and verify its hash
   again. For the reviewed USB path only, validate with
   `artifacts/nat-008/odin4 -d /dev/bus/usb/BUS/DEVICE -a artifacts/nat-008/SM-S921B_recovery-stock-odin.tar --check-only`.
   Abort if the returned device type does not match that model; do not bypass
   compatibility checks.
5. After verifying the actual PIT mapping, restore with the same command without
   `--check-only`. No other archive, --efs-clear, --bl-update, --allow-unknown,
   repartition or automatic reboot is allowed by this procedure.
6. Verify the restored bytes by the separately approved recovery procedure before
   attempting normal boot. A successful host parser run proves no device writes.

S-Boot/Odin compatibility on this S24 remains unmeasured; this tool is a candidate
restore utility, not a demonstrated rescue path. Keep the binary and prefix at
the recorded absolute paths (the dynamic RPATH binds that prefix).
