"""Cited Samsung register definitions as an independent test oracle (UI-007).

register_facts.json holds macro bodies copied verbatim from the pinned Samsung kernel. This module
(1) checks each entry against the source line it cites and (2) evaluates the bodies, so simulated
register images are encoded with Samsung's own definitions rather than with the C reader's constants.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
FACTS = HERE / "register_facts.json"
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Call, ast.Name, ast.Load,
            ast.Add, ast.Sub, ast.Mult, ast.LShift, ast.RShift, ast.BitAnd, ast.BitOr, ast.Invert,
            ast.Subscript, ast.USub)


def load(path: Path = FACTS) -> dict:
    return json.loads(path.read_text())


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text)
    return text.split("//", 1)[0].strip()


def _norm(text: str) -> str:
    return " ".join(text.split())


def define_line(entry: dict) -> str:
    params = "(" + ", ".join(entry["params"]) + ")" if "params" in entry else ""
    return f"#define {entry['name']}{params} {entry['body']}"


class Macros:
    """Evaluate the cited object- and function-like macros with plain integers."""

    def __init__(self, facts: dict):
        self.entries = {m["name"]: m for m in facts["macros"]}
        self._cache: dict = {}

    def _python(self, body: str) -> str:
        def repl(match):
            name = match.group(0)
            if name == "BIT":
                return "BIT"
            if name in self.entries:
                return f"M[{name!r}]" + ("" if "params" in self.entries[name] else "()")
            return name
        return _IDENT.sub(repl, body)

    def fn(self, name: str):
        if name in self._cache:
            return self._cache[name]
        entry = self.entries[name]
        params = entry.get("params", [])
        expr = self._python(entry["body"])
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED):
                raise ValueError(f"{name}: unsupported syntax {type(node).__name__}")
            if isinstance(node, ast.Name) and node.id not in params and node.id not in ("M", "BIT"):
                raise ValueError(f"{name}: unknown identifier {node.id}")
            if isinstance(node, ast.Constant) and not isinstance(node.value, (int, str)):
                raise ValueError(f"{name}: non-integer constant")
        code = compile(tree, f"<{name}>", "eval")

        def call(*args):
            if len(args) != len(params):
                raise TypeError(f"{name} takes {len(params)} arguments")
            env = {"M": _Lookup(self), "BIT": lambda n: 1 << n, "__builtins__": {}}
            env.update(zip(params, args))
            return eval(code, env) & 0xFFFFFFFFFFFFFFFF  # noqa: S307 - AST checked above

        self._cache[name] = call
        return call

    def __call__(self, name: str, *args) -> int:
        return self.fn(name)(*args)


class _Lookup:
    def __init__(self, macros):
        self.macros = macros

    def __getitem__(self, name):
        return self.macros.fn(name)


def find_reference(root: Path, source_id: str) -> Path | None:
    """The pinned checkout lives in the primary tree's references/, also from a worktree."""
    candidates = [root / "references" / source_id]
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=root, capture_output=True, text=True, timeout=10).stdout.strip()
        if common:
            candidates.append(Path(common).parent / "references" / source_id)
    except (OSError, subprocess.SubprocessError):
        pass
    for path in candidates:
        if (path / ".git").exists():
            return path
    return None


def source_text(repo: Path, revision: str, relpath: str) -> str | None:
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    result = subprocess.run(["git", "-C", str(repo), "show", f"{revision}:{relpath}"],
                            capture_output=True, env=env, timeout=30)
    return result.stdout.decode("utf-8", "replace") if result.returncode == 0 else None


def verify(facts: dict, repo: Path, revision: str, line_shift: dict | None = None,
           skip_unavailable: bool = False) -> tuple[list[str], int]:
    """Return (mismatches, number of checked entries) against the source at revision."""
    problems, files, checked, shift = [], {}, 0, line_shift or {}

    def line(relpath, number):
        if relpath not in files:
            files[relpath] = source_text(repo, revision, relpath)
        text = files[relpath]
        if text is None:
            return None
        lines = text.splitlines()
        number += shift.get(relpath, 0)
        return lines[number - 1] if 0 < number <= len(lines) else ""

    for kind in ("macros", "statements"):
        for entry in facts[kind]:
            got = line(entry["file"], entry["line"])
            if got is None:
                if not skip_unavailable:
                    problems.append(f"{entry['file']} unavailable at {revision}")
                continue
            checked += 1
            if kind == "macros" and _norm(_strip_comments(got)) != _norm(define_line(entry)):
                problems.append(f"{entry['file']}:{entry['line']}: expected {define_line(entry)!r}, found {got!r}")
            if kind == "statements" and _norm(entry["text"]) not in _norm(got):
                problems.append(f"{entry['file']}:{entry['line']}: {entry['text']!r} not in {got!r}")
    return problems, checked


class RegisterFile:
    """Sparse register images for the simulated MMIO blocks, encoded with the cited macros."""

    def __init__(self, macros: Macros):
        self.m = macros
        self.regions: dict[str, tuple[int, dict[int, int]]] = {}

    def region(self, name: str, size: int):
        self.regions.setdefault(name, (size, {}))
        return self

    def put(self, name: str, offset: int, value: int, shadow: int | None = None):
        size, words = self.regions[name]
        words[offset] = value & 0xFFFFFFFF
        if shadow is not None:
            words[offset + shadow] = value & 0xFFFFFFFF
        return self

    def decon(self, global_con: int, rsc_ch=(0x77777777, 0x77777777), rsc_win=(0x77777777, 0x77777777)):
        m = self.m
        self.region("main", 0x10000).region("win", 0x10000).region("wincon", 0x10000)
        self.put("main", m("GLOBAL_CON"), global_con)
        self.put("main", m("RSC_STATUS_0"), rsc_ch[0]).put("main", m("RSC_STATUS_0") + 4, rsc_ch[1])
        self.put("main", m("RSC_STATUS_2"), rsc_win[0]).put("main", m("RSC_STATUS_2") + 4, rsc_win[1])
        return self

    def window(self, win: int, channel: int, x0: int, y0: int, x1: int, y1: int, colormap=False, enable=True):
        m, shadow = self.m, self.m("SHADOW_OFFSET")
        con = m("WIN_CHMAP_F", channel) | (m("_WIN_EN_F") if enable else 0) | (m("WIN_MAPCOLOR_EN_F") if colormap else 0)
        self.put("wincon", m("DECON_CON_WIN", win), con, shadow)
        self.put("win", m("WIN_START_POSITION", win), m("WIN_STRPTR_Y_F", y0) | m("WIN_STRPTR_X_F", x0), shadow)
        self.put("win", m("WIN_END_POSITION", win), m("WIN_ENDPTR_Y_F", y1) | m("WIN_ENDPTR_X_F", x1), shadow)
        return self

    def dma(self, channel: int, *, fmt: int, base: int, src_w: int, src_h: int, img_w: int, img_h: int,
            x: int = 0, y: int = 0, stride: int = 0, ctrl_extra: int = 0):
        m, name = self.m, f"dma{channel}"
        shadow = m("DMA_SHD_OFFSET")
        self.region(name, 0x1000)
        self.put(name, m("RDMA_IN_CTRL_0"), m("IDMA_IMG_FORMAT", fmt) | ctrl_extra, shadow)
        self.put(name, m("RDMA_SRC_WIDTH"), m("IDMA_SRC_WIDTH", src_w), shadow)
        self.put(name, m("RDMA_SRC_HEIGHT"), m("IDMA_SRC_HEIGHT", src_h), shadow)
        self.put(name, m("RDMA_SRC_OFFSET"), m("IDMA_SRC_OFFSET_Y", y) | m("IDMA_SRC_OFFSET_X", x), shadow)
        self.put(name, m("RDMA_IMG_SIZE"), m("IDMA_IMG_HEIGHT", img_h) | m("IDMA_IMG_WIDTH", img_w), shadow)
        self.put(name, m("DMA_BASEADDR_P0"), base, shadow)
        self.put(name, m("DMA_SRC_STRIDE_0"), (m("DMA_STRIDE", stride) | m("DMA_STRIDE_SEL")) if stride else 0, shadow)
        return self

    def sysmmu(self, enabled_vms: set[int]):
        m = self.m
        self.region("sysmmu", 0xA000)
        for vm in range(2):
            self.put("sysmmu", m("MMU_VM_ADDR", m("REG_MMU_CTRL_VM"), vm),
                     m("CTRL_MMU_ENABLE") if vm in enabled_vms else 0)
        return self

    def script(self) -> list[str]:
        lines = []
        for name, (size, words) in self.regions.items():
            lines.append(f"region {name} {size:#x}")
            lines.extend(f"w {name} {off:#x} {val:#x}" for off, val in sorted(words.items()))
        return lines
