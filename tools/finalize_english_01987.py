#!/usr/bin/env python3
"""Translate legacy-only strings and apply isolated save-safe bug fixes."""

from __future__ import annotations

import csv
import re
import sys
from io import StringIO
from pathlib import Path

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TEXT_EXTS = {
    ".csv", ".json", ".variant", ".ship", ".skin", ".system", ".wpn",
    ".java", ".txt", ".md", ".faction", ".rules", ".properties",
}

OVERSEER_DESCRIPTION = (
    "The Overseer-class is a command cruiser commissioned by the Domain to "
    "serve as the flagship of small fleets without requiring the deployment "
    "of a capital ship. To fulfill this role, the Overseer features a larger-"
    "than-usual bridge and extensive command-and-control facilities. It is "
    "also well equipped both offensively and defensively, allowing it to "
    "fight on the front line or support allied vessels. A relatively rare "
    "design, the class is seen only occasionally in Hegemony service or in "
    "the fleets of wealthier mercenary companies."
)


def read_utf8(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig"), bom


def write_utf8(path: Path, text: str, bom: bool) -> None:
    raw = text.encode("utf-8")
    if bom:
        raw = b"\xef\xbb\xbf" + raw
    path.write_bytes(raw)


def patch_csv(path: Path, id_value: str, replacements: dict[str, str], type_value: str | None = None) -> None:
    text, bom = read_utf8(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    headers = rows[0]
    header_index = {name.strip().lower(): i for i, name in enumerate(headers)}
    id_col = header_index["id"]
    type_col = header_index.get("type")
    found = False

    for row in rows[1:]:
        if id_col >= len(row) or row[id_col] != id_value:
            continue
        if type_value is not None and (type_col is None or type_col >= len(row) or row[type_col] != type_value):
            continue
        for column, value in replacements.items():
            index = header_index[column.strip().lower()]
            while len(row) <= index:
                row.append("")
            row[index] = value
        found = True
        break

    if not found:
        raise RuntimeError(f"Unable to find {id_value!r} in {path}")

    buffer = StringIO(newline="")
    csv.writer(buffer, lineterminator=newline).writerows(rows)
    write_utf8(path, buffer.getvalue(), bom)


def patch_display_name(path: Path, display_name: str) -> None:
    text, bom = read_utf8(path)
    updated, count = re.subn(
        r'("displayName"\s*:\s*")[^"]*(")',
        lambda match: match.group(1) + display_name + match.group(2),
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Unable to patch displayName in {path}")
    write_utf8(path, updated, bom)


def replace_once(path: Path, old: str, new: str) -> None:
    text, bom = read_utf8(path)
    if old not in text:
        raise RuntimeError(f"Unable to find {old!r} in {path}")
    write_utf8(path, text.replace(old, new, 1), bom)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "BSC 0.1.98.7 English")

    # English restoration for 0.1.98.7-only content.
    patch_csv(
        root / "data/hulls/ship_data.csv",
        "BSC_Overseer",
        {
            "name": "Overseer",
            "designation": "Command Cruiser",
            "tech/manufacturer": "Domain Era",
        },
    )
    patch_csv(
        root / "data/hulls/wing_data.csv",
        "BSC_Bitzer_Drone_wing_six",
        {"role desc": "Point Defense"},
    )
    patch_csv(
        root / "data/strings/descriptions.csv",
        "BSC_Overseer",
        {"text1": OVERSEER_DESCRIPTION},
        type_value="SHIP",
    )
    patch_display_name(root / "data/variants/BSC_Overseer_Combat.variant", "Combat")
    patch_display_name(root / "data/variants/BSC_Overseer_Support.variant", "Support")

    # Isolated fixes from 0.1.98.8/0.1.98.85 that preserve old hull IDs and stats.
    replace_once(
        root / "data/hulls/BSC_Stobo.ship",
        '"spriteName": "graphics/hulls/fighters/BSC_stobo.png"',
        '"spriteName": "graphics/hulls/fighters/BSC_Stobo.png"',
    )
    patch_csv(
        root / "data/hulls/ship_data.csv",
        "BSC_Boggart",
        {
            "hints": "UNBOARDABLE",
            "tags": "remnant, auto_rec, codex_unlockable",
        },
    )
    replace_once(
        root / "data/variants/BSC_Overseer_Support.variant",
        '        "converted_hangar",',
        "",
    )

    remaining = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (path.suffix.lower() not in TEXT_EXTS and path.name != "mod_info.json"):
            continue
        try:
            text, _ = read_utf8(path)
        except UnicodeDecodeError:
            continue
        if CJK_RE.search(text):
            remaining.append(str(path.relative_to(root)))

    if remaining:
        raise RuntimeError("Chinese text remains in: " + ", ".join(remaining))

    print("English restoration and save-safe bug fixes completed; legacy hull IDs and stats remain intact.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
