from __future__ import annotations

import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".json", ".jsonl", ".csv", ".md", ".yaml", ".yml", ".txt"}
KEY_PYTHON_FILES = [
    ROOT / "scripts" / "verify_committed_text_integrity.py",
    ROOT / "scripts" / "normalize_text_line_endings.py",
    ROOT / "scripts" / "rewrite_clean_jsonl_lf.py",
    ROOT / "src" / "ecfinder" / "cli.py",
    ROOT / "src" / "ecfinder" / "pipeline" / "contracts.py",
    ROOT / "src" / "ecfinder" / "pipeline" / "gates.py",
    ROOT / "src" / "ecfinder" / "pipeline" / "orchestrator.py",
    ROOT / "src" / "ecfinder" / "pipeline" / "state.py",
    ROOT / "src" / "ecfinder" / "pipeline" / "report.py",
]


def iter_text_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in TEXT_EXTENSIONS
        and ".git" not in path.parts
        and "__pycache__" not in path.parts
    ]


def test_gitattributes_is_multiline() -> None:
    path = ROOT / ".gitattributes"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == [
        "* text=auto",
        "",
        "*.py text eol=lf",
        "*.json text eol=lf",
        "*.jsonl text eol=lf",
        "*.csv text eol=lf",
        "*.md text eol=lf",
        "*.yaml text eol=lf",
        "*.yml text eol=lf",
        "*.txt text eol=lf",
    ]


def test_text_files_do_not_contain_cr_bytes() -> None:
    offenders = [path.relative_to(ROOT).as_posix() for path in iter_text_files() if b"\r" in path.read_bytes()]
    assert offenders == []


def test_key_python_files_are_multiline() -> None:
    for path in KEY_PYTHON_FILES:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) > 20, path.relative_to(ROOT).as_posix()
        if text.startswith('"""'):
            docstring_end = text.find('"""', 3)
            assert docstring_end != -1
            after_docstring = text[docstring_end + 3 :].lstrip("\n")
            assert after_docstring.startswith("from __future__ import annotations\n"), path.relative_to(ROOT).as_posix()


def test_python_files_compile() -> None:
    for path in sorted(ROOT.rglob("*.py")):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        py_compile.compile(str(path), doraise=True)
