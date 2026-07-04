"""Small local full-text parser used by the streaming supervisor.

The parser reads lawful local PDF/HTML/text attachments and writes compact
chunk artifacts. It never copies or writes the original full text file.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ecfinder.state.common import normalize_text, sha256_text


RELEVANT_TERMS = [
    "pfas",
    "perfluoro",
    "polyfluoro",
    "fluorotelomer",
    "ftsa",
    "ftoh",
    "fosa",
    "fose",
    "fosaa",
    "pfos",
    "pfoa",
    "pfba",
    "pfca",
    "ftca",
    "pap",
    "dipap",
    "afff",
    "precursor",
    "biotransform",
    "biotransformation",
    "biodegradation",
    "transformation",
    "metabolite",
    "product",
    "soil",
    "sediment",
    "wetland",
    "groundwater",
    "aquifer",
]


class TextBlockParser(HTMLParser):
    BLOCK_TAGS = {"p", "li", "td", "th", "figcaption", "section", "div"}

    def __init__(self) -> None:
        super().__init__()
        self.depth = 0
        self.current_id = ""
        self.parts: list[str] = []
        self.blocks: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() not in self.BLOCK_TAGS:
            return
        if self.depth == 0:
            self.parts = []
            attr_map = {key.lower(): value or "" for key, value in attrs}
            self.current_id = attr_map.get("id", "") or attr_map.get("class", "")
        self.depth += 1

    def handle_data(self, data: str) -> None:
        if self.depth:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in self.BLOCK_TAGS or not self.depth:
            return
        self.depth -= 1
        if self.depth == 0:
            text = normalize_text(" ".join(self.parts))
            if len(text) >= 60:
                self.blocks.append({"section": "html_block", "section_id": self.current_id, "text": text})
            self.current_id = ""
            self.parts = []


def resolve_local_path(root: Path, path_text: str) -> Path | None:
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    return path


def parse_html_blocks(path: Path) -> list[dict[str, str]]:
    parser = TextBlockParser()
    parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    return parser.blocks


def parse_text_blocks(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks: list[dict[str, str]] = []
    for idx, raw_block in enumerate(text.replace("\r", "\n").split("\n\n"), start=1):
        block = normalize_text(raw_block)
        if len(block) >= 60:
            blocks.append({"section": "text_block", "section_id": f"block_{idx:03d}", "text": block})
    return blocks


def parse_pdf_blocks(path: Path) -> tuple[list[dict[str, str]], str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return [], "pypdf is not installed; PDF text extraction skipped"
    reader = PdfReader(str(path))
    blocks: list[dict[str, str]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = normalize_text(page.extract_text() or "")
        if len(text) >= 60:
            blocks.append({"section": "pdf_page", "section_id": f"page_{page_no}", "text": text})
    return blocks, ""


def parse_local_file(entry: dict[str, Any], path: Path) -> tuple[list[dict[str, str]], str]:
    suffix = path.suffix.lower()
    file_type = str(entry.get("file_type", "")).lower()
    if file_type == "pdf" or suffix == ".pdf":
        return parse_pdf_blocks(path)
    if file_type == "html" or suffix in {".html", ".htm", ".xhtml"}:
        return parse_html_blocks(path), ""
    if suffix in {".txt", ".md", ".xml"}:
        return parse_text_blocks(path), ""
    if file_type == "si":
        if suffix == ".pdf":
            return parse_pdf_blocks(path)
        if suffix in {".html", ".htm", ".xhtml"}:
            return parse_html_blocks(path), ""
        return parse_text_blocks(path), ""
    return [], f"unsupported local full-text file type: {file_type or suffix}"


def make_chunks(blocks: list[dict[str, str]], entry: dict[str, Any], metadata: dict[str, Any], run_prefix: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    source_id = str(metadata.get("source_id") or entry.get("source_id", ""))
    doi = str(metadata.get("doi") or entry.get("doi", ""))
    title = str(metadata.get("title") or entry.get("title", ""))
    for idx, block in enumerate(blocks, start=1):
        text = normalize_text(block["text"])
        lower = text.lower()
        if not any(term in lower for term in RELEVANT_TERMS):
            continue
        chunks.append(
            {
                "chunk_id": f"{run_prefix}_{source_id}_chunk_{idx:03d}",
                "source_id": source_id,
                "doi": doi,
                "title": title,
                "section": block.get("section", "local_fulltext_block"),
                "section_id": block.get("section_id", f"block_{idx:03d}"),
                "text": text,
                "word_count": len(text.split()),
                "char_count": len(text),
                "text_hash": sha256_text(text),
            }
        )
    return chunks
