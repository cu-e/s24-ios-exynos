#!/usr/bin/env python3
"""NAT-083: the one change to the donor userland that the project's RAM-disk numbering needs.

HackiOS boots with the big system image as /dev/md0 (rd=md0, the kernel's root) and the small image (init, rc, job list)
as /dev/md1, which stage0 mounts on /redwood.  The project delivers the big image over USB into the RAM reserve that the
payload registers as md1 (NAT-074/078), and md0 is the small payload ramdisk, so here it is the other way round:
rd=md1 makes the delivered APFS the root and stage0 has to mount /dev/md0.

The edit is a counted substitution on a pinned donor file: the base is checked against the hash in the pinned checkout, the
number of occurrences must equal the expected count, and anything else stops the script (a drifted base is not half-translated).

Donor: references/hakios @ 87bf4851bcc9cbb24fd79997820aa3661abe4ea5 (HackiOS userland, MIT; see references/hakios/LICENSE).  The patched file
keeps the donor's header comment with a note appended; the unified diff is written next to this script as stage0-md0.patch.

usage: python3 -I make_variant83.py RECIPE_DIR [--write-patch PATH]
   RECIPE_DIR is a copy of the staged donor recipe (tools/ios/stage_hakios_recipe.py); userland/src/stage0.c is replaced there
   by a new file (the original inode, possibly hard-linked to the pinned staging, is never written through).
"""
import argparse
import difflib
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PINNED = ROOT / "references/hakios/userland/src/stage0.c"
BASE_SHA256 = "18d12e7ea4fd51ccdd21a2b8e30fca4d893bfec1ffe7da28836a96843730ae2c"
BASE_GIT_BLOB = "3f04cc9687dc1e0b6624ae6d822b08f1bebff769"
DONOR_COMMIT = "87bf4851bcc9cbb24fd79997820aa3661abe4ea5"  # research/sources.json, source "hakios"

# (old, new, expected count)
SUBSTITUTIONS = [
    ("/dev/md1", "/dev/md0", 3),
]
NOTE = (" *\n"
        " * NAT-083 (this project): the donor's /dev/md1 is /dev/md0 here.  The project's md1 is the big system image (delivered over\n"
        " * USB, the kernel's root with rd=md1); md0 is the small image.  Counted substitution of the pinned donor file, see\n"
        " * docs/procedures/nat-083/make_variant83.py.\n"
        " */\n#include \"mini.h\"")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def translate(text):
    """-> (new text, list of (old, new, count))"""
    done = []
    for old, new, want in SUBSTITUTIONS:
        n = text.count(old)
        if n != want:
            raise ValueError("expected %d occurrence(s) of %r in the donor file, found %d: the base drifted" % (want, old, n))
        text = text.replace(old, new)
        done.append((old, new, n))
    marker = " */\n#include \"mini.h\""
    if text.count(marker) != 1:
        raise ValueError("the header comment end is not where the note goes (%d matches)" % text.count(marker))
    return text.replace(marker, NOTE), done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe", type=Path)
    ap.add_argument("--write-patch", type=Path)
    a = ap.parse_args(argv)
    base = PINNED.read_bytes()
    head = os.popen("git -C %s rev-parse HEAD" % (ROOT / "references/hakios")).read().strip()
    if head != DONOR_COMMIT:
        print("refused: references/hakios is at %s, not the pinned %s" % (head, DONOR_COMMIT), file=sys.stderr)
        return 2
    if sha256(base) != BASE_SHA256 or git_blob(base) != BASE_GIT_BLOB:
        print("refused: the pinned stage0.c is not the file this variant was written for (sha256 %s)" % sha256(base), file=sys.stderr)
        return 2
    staged = a.recipe / "userland/src/stage0.c"
    if sha256(staged.read_bytes()) != BASE_SHA256:
        print("refused: %s is not the pinned file" % staged, file=sys.stderr)
        return 2
    try:
        new, done = translate(base.decode())
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    data = new.encode()
    tmp = staged.with_name("stage0.c.nat083.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, staged)  # a new inode: a hard link to the pinned staging keeps the old bytes
    if sha256(PINNED.read_bytes()) != BASE_SHA256:
        print("the pinned donor file changed", file=sys.stderr)
        return 1
    diff = "".join(difflib.unified_diff(base.decode().splitlines(True), new.splitlines(True),
                                         "a/userland/src/stage0.c", "b/userland/src/stage0.c"))
    if a.write_patch:
        a.write_patch.write_text(diff)
    print(json.dumps(dict(file="userland/src/stage0.c", base_sha256=BASE_SHA256, base_git_blob=BASE_GIT_BLOB, new_sha256=sha256(data),
                          substitutions=[dict(old=o, new=n, count=c) for o, n, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
