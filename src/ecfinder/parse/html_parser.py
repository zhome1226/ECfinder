"""Simple HTML text extraction with optional BeautifulSoup."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path


class TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True
        if tag in {"p", "section", "h1", "h2", "h3", "tr", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False
        if tag in {"p", "section", "h1", "h2", "h3", "tr", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip() + " ")

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def extract_html_text(path: str | Path) -> str:
    html = Path(path).read_text(encoding="utf-8", errors="ignore")
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        return "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    except Exception:
        parser = TextHTMLParser()
        parser.feed(html)
        return parser.text()


def parse_html(path: str | Path, source_id: str) -> list[dict]:
    text = extract_html_text(path)
    return [
        {
            "source_id": source_id,
            "section_id": f"{source_id}_html_fulltext",
            "section": "html_fulltext",
            "page": None,
            "text": text,
            "parser": "html",
        }
    ]
