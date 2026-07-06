"""Shared helpers for external metadata search adapters."""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


USER_AGENT = "ECfinder-stage2.8-external-metadata-discovery/1.0"


@dataclass(frozen=True)
class AdapterResult:
    provider: str
    records: list[dict[str, Any]]
    available: bool
    error: str = ""


def fetch_json(url: str, timeout: int = 20) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def strip_markup(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(text).split())


def first_text(value: Any) -> str:
    if isinstance(value, list) and value:
        return strip_markup(str(value[0]))
    return strip_markup(str(value or ""))


def normalize_doi(value: Any) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.lower()


def normalize_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def year_from_date_parts(value: Any) -> str:
    try:
        return str(value["date-parts"][0][0])
    except (KeyError, IndexError, TypeError):
        return ""


def inverted_index_to_text(index: Any) -> str:
    if not isinstance(index, dict):
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in index.items():
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, int):
                    pairs.append((position, str(word)))
    return " ".join(word for _, word in sorted(pairs))


def query_url(base: str, params: dict[str, Any]) -> str:
    return base + "?" + urllib.parse.urlencode({key: value for key, value in params.items() if value not in {None, ""}})
