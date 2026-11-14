#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-157: nat036_msg() without a table of absolute pointers, for loader trees assembled from now on.

Why (NAT-151, docs/procedures/nat-151/README.md): the loader is built -fno-pic, linked at 0 (loader.ld) and run wherever S-Boot puts
it, with no runtime relocation. Code reaches its strings PC-relatively (adrp/add), but a `static const char *const site[]` table in
.rodata holds their link-time addresses (six R_AARCH64_ABS64 in ckpt3.c.o's .rela.rodata). NAT-151's loader found a bad checkpoint
site, took site[1] = 0x1f935 and faulted in fail() reading it (ESR 0x96000010, FAR 0x1f935) instead of printing the message.

This changes only the table's type: an array of characters (6 x 40 bytes) instead of an array of pointers, so site[i] is an
address computed from a PC-relative base and nothing in data needs relocating. (Switch cases returning the literals are not enough:
LLVM turns such a switch back into a table of pointers.) It changes only that function, refuses a tree whose function is not exactly the known text, and leaves pinned
images alone: it is applied to a tree right before ckpt3.c is compiled (wrap_cc()).

  python3 -B docs/procedures/nat-157/fix_msg.py TREE        # TREE = an image's source/ (contains shim/e1s-xnu/ckpt3.c)
"""
import sys
from pathlib import Path

OLD = '''const char *nat036_msg(int rc, uint32_t bad)
{
	static const char *const site[] = {
		"XNU checkpoint slot check failed", "XNU checkpoint site 1 check failed", "XNU checkpoint site 2 check failed",
		"XNU checkpoint site 3 check failed", "XNU checkpoint site 4 check failed", "XNU checkpoint site 5 check failed",
	};

	switch (rc) {
	case NAT031_SLOT_BAD: return site[0];
	case NAT031_SITE_BAD: return site[bad >= 1 && bad <= 5 ? bad : 0];
'''

NEW = '''const char *nat036_msg(int rc, uint32_t bad)
{
	/* NAT-157: the characters themselves, not pointers to them. The loader runs where S-Boot puts it without relocation, so a
	 * pointer stored in data keeps its link-time value (NAT-151 faulted reading one); site[i] is addressed PC-relatively. */
	static const char site[6][40] = {
		"XNU checkpoint slot check failed", "XNU checkpoint site 1 check failed", "XNU checkpoint site 2 check failed",
		"XNU checkpoint site 3 check failed", "XNU checkpoint site 4 check failed", "XNU checkpoint site 5 check failed",
	};

	switch (rc) {
	case NAT031_SLOT_BAD: return site[0];
	case NAT031_SITE_BAD: return site[bad >= 1 && bad <= 5 ? bad : 0];
'''


def fix_text(text):
    if text.count(OLD) != 1:
        raise SystemExit('nat036_msg is not the known table version (found %d): not patched' % text.count(OLD))
    return text.replace(OLD, NEW)


def apply(tree):
    p = Path(tree) / 'shim/e1s-xnu/ckpt3.c'
    p.write_text(fix_text(p.read_text()))
    return p


def wrap_cc(cc):
    """nat-052/build.py's cc(src, obj, extra, includes), fixing ckpt3.c just before it is compiled: after every prepare_tree layer
    of the chain (NAT-059, NAT-062 ... rewrite ckpt3.c in their own steps) and only in the image's own copy of the source tree.
    A build installs it with `b52.cc = fix_msg.wrap_cc(b52.cc)`."""
    def compiled(src, obj, extra, includes):
        if Path(src).name == 'ckpt3.c':
            p = Path(src)
            p.write_text(fix_text(p.read_text()))
        return cc(src, obj, extra, includes)
    compiled.nat157 = True
    return compiled


if __name__ == '__main__':
    print(apply(sys.argv[1]))
