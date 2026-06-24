"""Lawful raw full-text downloader with hash logging."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from ecfinder.download.fulltext_fallback import choose_fulltext_candidate
from ecfinder.utils.hashing import sha256_file
from ecfinder.utils.logging import read_jsonl, utc_now, write_jsonl


def download_url(url: str, destination: Path, timeout: int = 45) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "ECfinder/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec - URL comes from metadata
        content_type = response.headers.get("content-type", "")
        data = response.read()
    if "pdf" not in content_type.lower() and not data.startswith(b"%PDF"):
        raise ValueError(f"downloaded content is not a PDF: content_type={content_type}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return {"content_type": content_type, "bytes": len(data), "sha256": sha256_file(destination)}


def acquire_screened_sources(root: str | Path, limit: int | None = None, dry_run: bool = True) -> list[dict]:
    repo_root = Path(root)
    screened = {item.get("source_id"): item for item in read_jsonl(repo_root / "data" / "interim" / "screened_sources.jsonl")}
    sources = [item for item in read_jsonl(repo_root / "data" / "interim" / "search_results.jsonl")]
    outputs = []
    included = [source for source in sources if screened.get(source.get("source_id"), {}).get("decision") in {"include", "maybe"}]
    for source in included[:limit]:
        candidate = choose_fulltext_candidate(source)
        row = {
            "source_id": source.get("source_id"),
            "doi": source.get("doi"),
            "title": source.get("title"),
            "candidate_kind": candidate["kind"],
            "url": candidate["url"],
            "downloaded_at": utc_now(),
            "download_status": "dry_run" if dry_run else "not_attempted",
            "local_path": None,
            "sha256": None,
            "notes": candidate["reason"],
        }
        if not dry_run and candidate["kind"] == "pdf" and candidate["url"]:
            destination = repo_root / "data" / "raw" / "pdfs" / f"{source.get('source_id')}.pdf"
            try:
                info = download_url(candidate["url"], destination)
                row.update(
                    {
                        "download_status": "downloaded",
                        "local_path": str(destination.relative_to(repo_root)),
                        "sha256": info["sha256"],
                        "bytes": info["bytes"],
                        "content_type": info["content_type"],
                    }
                )
            except Exception as exc:
                row.update({"download_status": "failed", "notes": f"{candidate['reason']}; {type(exc).__name__}: {exc}"})
        outputs.append(row)
    write_jsonl(repo_root / "data" / "interim" / "download_status.jsonl", outputs)
    return outputs
