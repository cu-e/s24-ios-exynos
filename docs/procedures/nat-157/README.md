# NAT-157: the loader's checkpoint messages without absolute pointers (host-test)

Evidence kind: host-test. No device was used. NAT-157 supersedes NAT-155, whose dependency on the open NAT-151 fail record cannot
be met.

## Defect

NAT-151's loader found a bad kernel checkpoint site. It should then have printed "XNU checkpoint site 1 check failed"; instead it
took a data abort in `fail()` (ESR 0x96000010, FAR 0x1f935). See `docs/procedures/nat-151/README.md` for the full analysis:
- the loader is built `-fno-pic`, linked at 0 and run at S-Boot's address (0x800b0000 in NAT-151) with no relocation;
- `nat036_msg()` returned the slot/site messages from `static const char *const site[]`, an array of six link-time addresses in
  `.rodata` (`R_AARCH64_ABS64`);
- site[1] held 0x1f935, the link-time address of exactly that message.

## Fix (`fix_msg.py`)

Only the table's type changes: `static const char site[6][40]`. The array now holds the characters, not pointers to them, so
`site[i]` is computed from a PC-relative base, and nothing in data needs relocating. A first attempt returned the literals from
`switch` cases. That is not enough: LLVM turns such a switch back into a table of pointers (5 `ABS64` remained), and the test
caught it.

`fix_text()` refuses any `nat036_msg()` that is not exactly the known table version, and refuses to run twice.

Pinned images and the pinned NAT-036 source (decision 0024, NAT-036 evidence) are not touched. `wrap_cc(cc)` applies the fix to the
image's own copy of `ckpt3.c` immediately before that file is compiled, after every `prepare_tree` layer of the chain. A build
installs it on every `nat-052/build.py` module instance in its chain. The chain holds two, loaded with `module_from_spec` and not all
of them in `sys.modules`; `build_demo.py:chain_modules()` finds them through module attributes.

## Gate (`relocscan.py`)

`relocscan.py` lists every `R_AARCH64_ABS*` in an image's loader objects (`NN-*.o`). Only `start.S`'s Image-header size field
(`.quad _payload_start` in `.text.head`) is allowed; it is 0-based by definition. Anything else returns rc 1.

| Image | Absolute relocations | Not allowed |
| --- | --- | --- |
| scH, NAT-152 build-001 (ran in NAT-153) | 7 | 6, all `10-ckpt3.c.o .rela.rodata` (the table) |
| scH rebuilt with the hook (`build_demo.py`, artifacts/nat-157/build-001) | 1 | 0 |

## End-to-end host build (`build_demo.py`)

NAT-152's scH build with the hook installed, host only, never written to the phone:
- relocscan: 1 relocation, 0 not allowed; the image's `ckpt3.c` has the character array;
- NAT-152's gate passed inside the build: the loader's checkpoint check rc 0 and the constants on the NAT-143 symbols;
- against NAT-152 build-001, only `10-ckpt3.c.o` differs among the loader objects. `payload.adt8.bin` is byte-identical
  (7ca29519…), while the loader Image and `Image.payload` differ (the loader is inside them).

## Tests (`test_nat157.py`, 5 OK)

- Old and new `nat036_msg()`, each compiled alone for the host with the rc enums of the tree's own headers (9 values), return the same
  string for all 140 combinations of rc −2…11 and bad {0–7, 99, 0xffffffff}; rc 2 / bad 1 gives NAT-151's message.
- Unknown text or a second application is refused.
- `ckpt3.c` compiled with the loader's flags (nat-022 FLAGS without -Werror, NO_SIMD, the stop macro), as nat-052 compiles it:
  old 6 absolute relocations, new 0.
- relocscan on the scH image finds the six and allows the header's.
- `wrap_cc` changes `ckpt3.c` only, before it is compiled.

## For the next native image

The next image build installs `wrap_cc` on its chain's nat-052 modules and runs `relocscan.py` as a gate, next to
`check_loader_sites.py`. Then a failed loader check prints its message instead of faulting. The NAT-044 deadline still ends such a
run in Download Mode.
