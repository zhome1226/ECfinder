"""Normalize repository text files to LF line endings."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".json", ".jsonl", ".csv", ".md", ".yaml", ".yml", ".txt"}
SKIP_PARTS = {".git", "__pycache__"}
SKIP_PREFIXES = {
    ROOT / "data" / "raw" / "pdfs",
}


def should_skip(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return True
    return any(path == prefix or prefix in path.parents for prefix in SKIP_PREFIXES)


def is_text_target(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS and not should_skip(path)


def normalize_bytes(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def main() -> int:
    changed: list[Path] = []
    for path in sorted(ROOT.rglob("*")):
        if not is_text_target(path):
            continue
        try:
            data = path.read_bytes()
            data.decode("utf-8")
        except UnicodeDecodeError:
            print(f"skip_non_utf8 {path.relative_to(ROOT).as_posix()}")
            continue
        normalized = normalize_bytes(data)
        if normalized != data:
            path.write_bytes(normalized)
            changed.append(path)
    for path in changed:
        print(f"normalized {path.relative_to(ROOT).as_posix()}")
    print(f"normalized_file_count {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
