"""PDF parsing with optional pdfplumber/pypdf backends."""

from __future__ import annotations

from pathlib import Path


def parse_pdf(path: str | Path, source_id: str) -> list[dict]:
    pdf_path = Path(path)
    try:
        import pdfplumber  # type: ignore

        sections = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for index, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                sections.append(
                    {
                        "source_id": source_id,
                        "section_id": f"{source_id}_page_{index}",
                        "section": f"page_{index}",
                        "page": index,
                        "text": text,
                        "parser": "pdfplumber",
                    }
                )
        return sections
    except Exception:
        pass

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(pdf_path))
        return [
            {
                "source_id": source_id,
                "section_id": f"{source_id}_page_{index}",
                "section": f"page_{index}",
                "page": index,
                "text": page.extract_text() or "",
                "parser": "pypdf",
            }
            for index, page in enumerate(reader.pages, start=1)
        ]
    except Exception as exc:
        return [
            {
                "source_id": source_id,
                "section_id": f"{source_id}_parse_error",
                "section": "parse_error",
                "page": None,
                "text": "",
                "parser": "none",
                "error": f"{type(exc).__name__}: {exc}",
            }
        ]
