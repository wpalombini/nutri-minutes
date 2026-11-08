#!/usr/bin/env python3
"""Check the Nutri Minutes design tokens.

Reads every *.tokens.json file next to this script (or in the directory given
as the first argument), builds the light and dark token sets, resolves
aliases and checks every recorded contrast pair against its WCAG 2.2 AA
threshold. Standard library only. Exits 1 on any failure.

Run: python3 -I design/tokens/check_contrast.py
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

EXT = "io.github.wpalombini.nutri-minutes"
# WCAG 2.2 AA: 1.4.3 text, 1.4.11 non-text (control borders, icons, focus, graphics).
REQUIRED = {"text": 4.5, "non-text": 3.0}
SHARED = ("base.tokens.json", "roles.tokens.json")
THEMES = {"light": "color.light.tokens.json", "dark": "color.dark.tokens.json"}
ALIAS = re.compile(r"^\{([^{}]+)\}$")

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"FAIL {msg}")


# --- contrast (same maths as the design plan's appendix script) ---------------
def lum(h: str) -> float:
    h = h.lstrip("#")
    c = [int(h[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


# --- loading and merging ------------------------------------------------------
def merge(into: dict[str, Any], src: dict[str, Any], where: str, path: str = "") -> None:
    for key, val in src.items():
        here = f"{path}.{key}" if path else key
        if key not in into:
            into[key] = val
        elif isinstance(val, dict) and isinstance(into[key], dict) and "$value" not in val and "$value" not in into[key]:
            merge(into[key], val, where, here)
        elif key.startswith("$"):
            continue  # group metadata repeated across files; the first file's wins
        else:
            fail(f"{where}: '{here}' is defined in more than one file")


def tokens(tree: dict[str, Any], path: tuple[str, ...] = (), gtype: str | None = None):
    """Yield (path, token, inherited group $type) for every token in a tree."""
    gtype = tree.get("$type", gtype)
    for key, val in tree.items():
        if key.startswith("$") or not isinstance(val, dict):
            continue
        if any(ch in key for ch in "{}."):
            fail(f"invalid name '{key}' under {'.'.join(path) or 'root'}")
        if "$value" in val:
            yield path + (key,), val, gtype
        else:
            yield from tokens(val, path + (key,), gtype)


class Theme:
    def __init__(self, name: str, tree: dict[str, Any]):
        self.name = name
        self.index = {".".join(p): (tok, g) for p, tok, g in tokens(tree)}

    def type_of(self, path: str, seen: tuple[str, ...] = ()) -> str | None:
        tok, gtype = self.index[path]
        if "$type" in tok:
            return tok["$type"]
        m = ALIAS.match(tok["$value"]) if isinstance(tok["$value"], str) else None
        if m and m.group(1) in self.index and m.group(1) not in seen:
            return self.type_of(m.group(1), seen + (path,))
        return gtype

    def resolve(self, value: Any, chain: tuple[str, ...]) -> Any:
        if isinstance(value, str) and (m := ALIAS.match(value)):
            target = m.group(1)
            if target in chain:
                raise ValueError("circular reference " + " -> ".join(chain + (target,)))
            if target not in self.index:
                raise ValueError(f"'{chain[-1]}' refers to missing token '{target}'")
            return self.resolve(self.index[target][0]["$value"], chain + (target,))
        if isinstance(value, dict):
            return {k: self.resolve(v, chain) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v, chain) for v in value]
        return value


def color_hex(theme: Theme, path: str, value: Any) -> str | None:
    """Validate a resolved colour value and return its hex, or None if invalid."""
    if not isinstance(value, dict) or value.get("colorSpace") != "srgb":
        fail(f"{theme.name}: {path} is not an sRGB colour object")
        return None
    comps = value.get("components")
    if not (isinstance(comps, list) and len(comps) == 3 and all(isinstance(c, (int, float)) and 0 <= c <= 1 for c in comps)):
        fail(f"{theme.name}: {path} needs three sRGB components between 0 and 1")
        return None
    derived = "#" + "".join(f"{round(c * 255):02x}" for c in comps)
    hexv = value.get("hex", derived)
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hexv) or hexv.lower() != derived:
        fail(f"{theme.name}: {path} hex {hexv} does not match its components ({derived})")
    return derived


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    files = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*.tokens.json"))}
    expected = set(SHARED) | set(THEMES.values())
    if set(files) != expected:
        fail(f"expected token files {sorted(expected)}, found {sorted(files)}")
        return 1

    theme_paths = {t: {".".join(p) for p, _, _ in tokens(files[f])} for t, f in THEMES.items()}
    if theme_paths["light"] != theme_paths["dark"]:
        fail(f"light and dark colour roles differ: {sorted(theme_paths['light'] ^ theme_paths['dark'])}")

    checked = 0
    for name, theme_file in THEMES.items():
        tree: dict[str, Any] = {}
        for f in (*SHARED, theme_file):
            merge(tree, copy.deepcopy(files[f]), name)
        theme = Theme(name, tree)

        # Every token has a type and every alias resolves.
        resolved: dict[str, Any] = {}
        for path, (tok, _) in theme.index.items():
            if theme.type_of(path) is None:
                fail(f"{name}: {path} has no $type (own, alias or group)")
            try:
                resolved[path] = theme.resolve(tok["$value"], (path,))
            except ValueError as e:
                fail(f"{name}: {e}")
        for path in resolved:
            if theme.type_of(path) == "color":
                color_hex(theme, path, resolved[path])

        # Every colour role is a surface, decorative, or has contrast records.
        print(f"\n{name}")
        for path in sorted(theme_paths[name]):
            tok = theme.index[path][0]
            ext = tok.get("$extensions", {}).get(EXT, {})
            records = ext.get("contrast", [])
            if not records:
                if not (path.startswith("surface.") or ext.get("decorative") is True):
                    fail(f"{name}: {path} has no contrast record and is not a surface or decorative")
                continue
            fg = color_hex(theme, path, resolved.get(path))
            for rec in records:
                m = ALIAS.match(str(rec.get("on", "")))
                kind, need, noted = rec.get("kind"), rec.get("min"), rec.get("ratio")
                label = f"{name}: {path} on {rec.get('on')}"
                if not m or m.group(1) not in resolved:
                    fail(f"{label}: 'on' must be an alias to a colour token")
                    continue
                if kind not in REQUIRED or not isinstance(need, (int, float)) or need < REQUIRED[kind]:
                    fail(f"{label}: {kind!r} pairs need at least {REQUIRED.get(kind, '?')}:1, recorded min is {need}")
                    continue
                bg = color_hex(theme, m.group(1), resolved[m.group(1)])
                if fg is None or bg is None:
                    continue
                for p in (path, m.group(1)):
                    if resolved[p].get("alpha", 1) != 1:
                        fail(f"{label}: {p} is translucent, so its contrast depends on what is behind it")
                r = ratio(fg, bg)
                ok = r >= need
                checked += 1
                print(f"  {'pass' if ok else 'FAIL'}  {r:5.2f} (needs {need})  {path} on {m.group(1)}  [{rec.get('use', kind)}]")
                if not ok:
                    fail(f"{label}: {r:.2f} is below {need}")
                if noted != round(r, 2):
                    fail(f"{label}: recorded ratio {noted} but computed {r:.2f}")

    print(f"\n{checked} pairs checked, {len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
