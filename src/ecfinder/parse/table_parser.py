"""Table extraction helpers."""

from __future__ import annotations

from pathlib import Path


def extract_pdf_tables(path: str | Path, source_id: str) -> list[dict]:
    try:
        import pdfplumber  # type: ignore
    except Exception as exc:
        return [{"source_id": source_id, "error": f"pdfplumber_unavailable: {exc}", "rows": []}]

    tables = []
    with pdfplumber.open(str(path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table_no, table in enumerate(page.extract_tables() or [], start=1):
                tables.append(
                    {
                        "source_id": source_id,
                        "table_id": f"{source_id}_p{page_no}_t{table_no}",
                        "page": page_no,
                        "rows": table,
                    }
                )
    return tables
