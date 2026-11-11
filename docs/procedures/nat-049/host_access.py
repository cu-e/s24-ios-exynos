#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-049: can this user open the NAT-041 monitor device (USB 1209:0001) once the phone shows it?

    host_access.py [--check] [--rules-dir DIR ...]

The collector (s24_logd.py) talks to the monitor with libusb control transfers, which needs write access to the device's usbfs
node. The node is created by udev for a device nobody has a rule for as `root:root 0664`, so an ordinary user gets EACCES: the
collector would record `device-access-denied` and the first unattended log run would be wasted. The existing host rule
(/etc/udev/rules.d/51-android.rules) covers only the phone's own identities, 04e8 and 18d1, which the collector refuses by design.

This module reads the udev rule files (nothing else; it does not open any USB node and runs no command) and says whether some rule
for idVendor 1209 / idProduct 0001 gives the calling user write access: `MODE` with the other-write bit, or the group-write bit
with a `GROUP` the user belongs to, or the owner-write bit with `OWNER` the user, or `TAG+="uaccess"` (logind ACL for the seat
user). The rule shipped with the project is docs/procedures/nat-049/70-s24-usbmon.rules; installing it needs root and is outside
this tool. `find_rule` is a reading of rule text, not proof that udev applied it; the proof is the first real open.

Exit status of --check: 0 = a rule grants access, 2 = none does."""
import argparse
import grp
import json
import os
import pwd
import re
import sys
from pathlib import Path

VID, PID = "1209", "0001"
# udev(7): /usr/lib, /usr/local/lib, /run and /etc (and the legacy /lib, which is a link to /usr/lib on merged-usr systems)
RULE_DIRS = ("/etc/udev/rules.d", "/run/udev/rules.d", "/usr/local/lib/udev/rules.d", "/usr/lib/udev/rules.d", "/lib/udev/rules.d")


def logical_lines(text):
    """Rule lines with backslash continuations joined and comments dropped."""
    out, cur = [], ""
    for raw in text.splitlines():
        line = raw.strip()
        if cur:
            line = cur + line
            cur = ""
        if line.endswith("\\"):
            cur = line[:-1] + " "
            continue
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _matches(line, key, value):
    return re.search(r'(?i)\b(?:ATTRS?|ENV)\{%s\}\s*==\s*"%s"' % (key, re.escape(value)), line) is not None


def grants(line, user, groups):
    """-> a short description of the access the rule line gives `user` (member of `groups`), or None."""
    if not (_matches(line, "idVendor", VID) and _matches(line, "idProduct", PID)):
        return None
    if re.search(r'TAG\+="uaccess"', line):
        return "uaccess"
    m = re.search(r'\bMODE\s*=\s*"([0-7]{3,4})"', line)
    if not m:
        return None
    mode = int(m.group(1), 8)
    owner = re.search(r'\bOWNER\s*=\s*"([^"]+)"', line)
    group = re.search(r'\bGROUP\s*=\s*"([^"]+)"', line)
    if mode & 0o002:
        return "MODE=%s (any user)" % m.group(1)
    if group and group.group(1) in groups and mode & 0o020:
        return 'MODE=%s GROUP="%s"' % (m.group(1), group.group(1))
    if owner and owner.group(1) == user and mode & 0o200:
        return 'MODE=%s OWNER="%s"' % (m.group(1), user)
    return None


def current_user():
    uid = os.getuid()
    name = pwd.getpwuid(uid).pw_name
    gids = set(os.getgroups()) | {pwd.getpwuid(uid).pw_gid}
    return name, {grp.getgrgid(g).gr_name for g in gids}


def find_rule(dirs=RULE_DIRS, user=None, groups=None):
    """-> dict(file, line, grant) of the first rule that gives the user access to 1209:0001, or None. Unreadable files are skipped."""
    if user is None:
        user, groups = current_user()
    for d in dirs:
        for f in sorted(Path(d).glob("*.rules")):                 # glob() yields nothing for a missing or unreadable directory
            try:
                text = f.read_text()
            except OSError:
                continue
            for line in logical_lines(text):
                g = grants(line, user, groups)
                if g:
                    return dict(file=str(f), line=line, grant=g)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="(default) print the finding")
    ap.add_argument("--rules-dir", action="append", help="rule directory to read (repeatable); default the udev directories of udev(7)")
    a = ap.parse_args(argv)
    user, groups = current_user()
    found = find_rule(tuple(a.rules_dir) if a.rules_dir else RULE_DIRS, user, groups)
    print(json.dumps(dict(vid_pid="%s:%s" % (VID, PID), user=user, found=found, groups=sorted(groups)), indent=1))
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
