#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Mutation pass for NAT-108: mutate analyze_nat108.py, build.py, build_sc1_hb_root.py, and derive108.py
and require test_nat108.py to kill every non-equivalent mutant. Host-only."""
import importlib.util
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REL = "docs/procedures/nat-108"
TARGETS = (
    ("py", REL + "/analyze_nat108.py"),
    ("py", REL + "/build.py"),
    ("py", REL + "/build_sc1_hb_root.py"),
    ("py", REL + "/derive108.py"),
)
TESTS = ("test_nat108.py",)
FIRST = {t: "test_nat108.py" for _, t in TARGETS}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M104 = _load("nat108_m104", os.path.join(ROOT, "docs", "procedures", "nat-104", "mutate_nat104.py"))


def make_tree(dst, snapshot):
    proc = os.path.join(dst, REL)
    os.makedirs(os.path.dirname(proc))
    shutil.copytree(snapshot, proc)
    real = os.path.join(ROOT, "docs", "procedures")
    for name in os.listdir(real):
        if name != "nat-108":
            os.symlink(os.path.join(real, name), os.path.join(dst, "docs", "procedures", name))
    for top in ("artifacts", "tools", "references"):
        os.symlink(os.path.join(ROOT, top), os.path.join(dst, top))
    os.symlink(os.path.join(ROOT, "docs", "decisions"), os.path.join(dst, "docs", "decisions"))
    return dst


def main():
    M104.HERE = HERE
    M104.REL = REL
    M104.TARGETS = TARGETS
    M104.TESTS = TESTS
    M104.FIRST = FIRST
    M104.make_tree = make_tree
    return M104.main()


if __name__ == "__main__":
    sys.exit(main())
