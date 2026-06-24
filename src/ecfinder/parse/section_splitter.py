"""Split parsed text into coarse scientific sections."""

from __future__ import annotations

import re


SECTION_RE = re.compile(r"^(abstract|introduction|methods?|results?|discussion|conclusions?|references|supporting information)\b", re.I)


def split_sections(source_id: str, text: str) -> list[dict]:
    current = {"heading": "body", "lines": []}
    sections = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if SECTION_RE.match(stripped) and current["lines"]:
            sections.append(current)
            current = {"heading": stripped[:120], "lines": []}
        current["lines"].append(stripped)
    if current["lines"]:
        sections.append(current)
    return [
        {
            "source_id": source_id,
            "section_id": f"{source_id}_section_{index}",
            "section": section["heading"],
            "page": None,
            "text": "\n".join(section["lines"]),
            "parser": "section_splitter",
        }
        for index, section in enumerate(sections, start=1)
    ]
