"""Hash helpers for stable provenance IDs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    joined = "\n".join("" if part is None else str(part) for part in parts)
    return f"{prefix}_{sha256_text(joined)[:length]}"


def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    value = doi.strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    value = re.sub(r"^doi:\s*", "", value)
    return value.strip() or None


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    value = re.sub(r"[^\w\s-]", " ", title.lower())
    stopwords = {"a", "an", "the", "in", "of", "for", "on", "to", "and", "with", "by", "et", "al"}
    tokens = [token for token in value.split() if token not in stopwords]
    return " ".join(tokens)
