#!/usr/bin/env python3
"""Create an English-facing BSC 0.1.98.7 without changing gameplay data.

The Chinese 0.1.98.7 folder is copied verbatim. Only string values/cells that
contain CJK characters are replaced. English text is taken from the newer
English build first, then from an archived English 0.1.98.4 build for content
that the newer release removed (including Buffalo Mk.III).
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
PAIR_RE = re.compile(
    r'(?P<prefix>"(?P<key>[^"\\]+)"\s*:\s*")'
    r'(?P<value>(?:\\.|[^"\\])*)'
    r'(?P<suffix>")'
)
TEXT_EXTS = {
    ".csv", ".json", ".variant", ".ship", ".skin", ".system", ".wpn",
    ".java", ".txt", ".md", ".faction", ".rules", ".properties",
}


def read_text(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return raw.decode(encoding), bom
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", raw, 0, 1, f"Unable to decode {path}")


def write_text(path: Path, text: str, bom: bool) -> None:
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def get_version(mod_info: Path) -> str:
    text, _ = read_text(mod_info)
    match = re.search(r'["\']?version["\']?\s*:\s*["\']([^"\']+)', text)
    return match.group(1) if match else ""


def find_mod_roots(repo: Path) -> tuple[Path, Path]:
    roots = []
    for info in repo.rglob("mod_info.json"):
        if any(part in {".git", ".github", "analysis", "BSC 0.1.98.7 English"} for part in info.parts):
            continue
        roots.append((info.parent, get_version(info)))

    old = next((path for path, version in roots if version == "0.1.98.7"), None)
    new = next((path for path, version in roots if version == "0.1.98.85"), None)
    if old is None or new is None:
        found = ", ".join(f"{p}={v}" for p, v in roots)
        raise RuntimeError(f"Could not identify both source folders. Found: {found}")
    return old, new


def contains_cjk(value: str) -> bool:
    return bool(CJK_RE.search(value or ""))


def clean_candidate(value: str | None) -> str | None:
    if value is None or value == "" or contains_cjk(value):
        return None
    return value


def source_paths(rel: Path, new_root: Path, archive_root: Path) -> list[Path]:
    paths = []
    for root in (new_root, archive_root):
        candidate = root / rel
        if candidate.is_file():
            paths.append(candidate)
    return paths


def detect_csv_key(headers: list[str]) -> list[int]:
    normalized = [h.strip().lower() for h in headers]
    key_names = [
        ("id", "type"),
        ("id",),
        ("variantid",),
        ("variant id",),
        ("hullid",),
        ("hull id",),
        ("weapon id",),
        ("wing id",),
        ("system id",),
    ]
    for names in key_names:
        if all(name in normalized for name in names):
            return [normalized.index(name) for name in names]
    return []


def row_key(row: list[str], key_indexes: list[int], fallback_index: int) -> tuple[str, ...]:
    if key_indexes and all(i < len(row) for i in key_indexes):
        return tuple(row[i] for i in key_indexes)
    return (f"__row_{fallback_index}",)


def read_csv_rows(path: Path) -> tuple[list[list[str]], bool, str]:
    text, bom = read_text(path)
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(text.splitlines()))
    return rows, bom, newline


def build_csv_map(path: Path, key_indexes: list[int]) -> dict[tuple[str, ...], list[str]]:
    rows, _, _ = read_csv_rows(path)
    result: dict[tuple[str, ...], list[str]] = {}
    for index, row in enumerate(rows[1:], start=1):
        result[row_key(row, key_indexes, index)] = row
    return result


def merge_csv(target: Path, sources: list[Path]) -> tuple[int, list[str]]:
    rows, bom, newline = read_csv_rows(target)
    if not rows:
        return 0, []
    headers = rows[0]
    key_indexes = detect_csv_key(headers)
    source_maps = [build_csv_map(path, key_indexes) for path in sources]
    replacements = 0
    unresolved: list[str] = []

    for index, row in enumerate(rows[1:], start=1):
        key = row_key(row, key_indexes, index)
        candidates = [mapping.get(key) for mapping in source_maps]
        for col, value in enumerate(row):
            if not contains_cjk(value):
                continue
            replacement = None
            for candidate in candidates:
                if candidate is None or col >= len(candidate):
                    continue
                replacement = clean_candidate(candidate[col])
                if replacement is not None:
                    break
            if replacement is None:
                unresolved.append(f"row={key!r} column={headers[col] if col < len(headers) else col}: {value}")
            else:
                row[col] = replacement
                replacements += 1

    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerows(rows)
    write_text(target, buffer.getvalue(), bom)
    return replacements, unresolved


def keyed_values(text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for match in PAIR_RE.finditer(text):
        result[match.group("key")].append(match.group("value"))
    return result


def merge_keyed_text(target: Path, sources: list[Path]) -> tuple[int, list[str]]:
    text, bom = read_text(target)
    source_maps = []
    for source in sources:
        source_text, _ = read_text(source)
        source_maps.append(keyed_values(source_text))

    occurrences: Counter[str] = Counter()
    replacements = 0
    unresolved: list[str] = []

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        key = match.group("key")
        value = match.group("value")
        occurrence = occurrences[key]
        occurrences[key] += 1
        if not contains_cjk(value):
            return match.group(0)

        replacement = None
        for source_map in source_maps:
            values = source_map.get(key, [])
            if occurrence < len(values):
                replacement = clean_candidate(values[occurrence])
                if replacement is not None:
                    break
            # Human-facing keys are generally unique. This fallback handles
            # harmless formatting/reordering between releases.
            if len(values) == 1:
                replacement = clean_candidate(values[0])
                if replacement is not None:
                    break

        if replacement is None:
            unresolved.append(f"key={key} occurrence={occurrence}: {value}")
            return match.group(0)
        replacements += 1
        return match.group("prefix") + replacement + match.group("suffix")

    merged = PAIR_RE.sub(replace, text)
    write_text(target, merged, bom)
    return replacements, unresolved


def merge_plain_text(target: Path, sources: list[Path]) -> tuple[int, list[str]]:
    """Conservative fallback for line-oriented files.

    Replace a Chinese-bearing line only when a source file has a line at the
    same index containing no Chinese. Otherwise leave it for the report.
    """
    text, bom = read_text(target)
    lines = text.splitlines(keepends=True)
    source_lines = []
    for source in sources:
        source_text, _ = read_text(source)
        source_lines.append(source_text.splitlines(keepends=True))

    replacements = 0
    unresolved = []
    for index, line in enumerate(lines):
        if not contains_cjk(line):
            continue
        replacement = None
        for candidates in source_lines:
            if index < len(candidates) and not contains_cjk(candidates[index]):
                replacement = candidates[index]
                break
        if replacement is None:
            unresolved.append(f"line={index + 1}: {line.strip()}")
        else:
            lines[index] = replacement
            replacements += 1
    write_text(target, "".join(lines), bom)
    return replacements, unresolved


def remaining_cjk_files(root: Path) -> list[dict[str, object]]:
    remaining = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (path.suffix.lower() not in TEXT_EXTS and path.name != "mod_info.json"):
            continue
        try:
            text, _ = read_text(path)
        except UnicodeDecodeError:
            continue
        matches = list(CJK_RE.finditer(text))
        if matches:
            pos = matches[0].start()
            remaining.append({
                "path": str(path.relative_to(root)),
                "cjk_chars": len(matches),
                "excerpt": text[max(0, pos - 100):pos + 300].replace("\n", "\\n"),
            })
    return remaining


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    archive_root = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None
    if archive_root is None or not (archive_root / "mod_info.json").is_file():
        raise RuntimeError("Pass the archived English BSC folder as the second argument")

    old_root, new_root = find_mod_roots(repo)
    output_root = repo / "BSC 0.1.98.7 English"
    if output_root.exists():
        shutil.rmtree(output_root)
    shutil.copytree(old_root, output_root)

    report: dict[str, object] = {
        "old_root": str(old_root.relative_to(repo)),
        "new_root": str(new_root.relative_to(repo)),
        "archive_root": str(archive_root),
        "output_root": str(output_root.relative_to(repo)),
        "files": [],
    }
    totals = Counter()

    for target in sorted(output_root.rglob("*")):
        if not target.is_file():
            continue
        rel = target.relative_to(output_root)
        if target.suffix.lower() not in TEXT_EXTS and target.name != "mod_info.json":
            continue
        text, _ = read_text(target)
        if not contains_cjk(text):
            continue

        sources = source_paths(rel, new_root, archive_root)
        if target.suffix.lower() == ".csv":
            changed, unresolved = merge_csv(target, sources)
            method = "csv-cell"
        elif target.suffix.lower() in {".json", ".variant", ".ship", ".skin", ".system", ".wpn", ".faction"} or target.name == "mod_info.json":
            changed, unresolved = merge_keyed_text(target, sources)
            method = "keyed-string"
        else:
            changed, unresolved = merge_plain_text(target, sources)
            method = "line"

        totals["files_processed"] += 1
        totals["strings_replaced"] += changed
        totals["unresolved_entries"] += len(unresolved)
        report["files"].append({
            "path": str(rel),
            "sources": [str(path) for path in sources],
            "method": method,
            "replacements": changed,
            "unresolved": unresolved,
        })

    remaining = remaining_cjk_files(output_root)
    report["totals"] = dict(totals)
    report["remaining_cjk_files"] = remaining

    report_path = repo / "analysis/bsc_english_build_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "output": str(output_root),
        "totals": dict(totals),
        "remaining_cjk_files": len(remaining),
    }, indent=2))
    # Keep the generated build for inspection even when entries remain.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
