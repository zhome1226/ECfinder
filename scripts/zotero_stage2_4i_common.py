"""Shared helpers for Stage 2.4i Zotero automation.

This module intentionally treats Zotero as an external lawful-access tool. It
never writes Zotero's SQLite database and never attempts paywall bypass.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "data" / "local_fulltext" / "stage2_4b" / "fulltext_manifest.jsonl"
BATCH_DIR = ROOT / "data" / "batches"
REPORTS_DIR = ROOT / "reports"
STATE_DIR = ROOT / "data" / "state"
ZOTERO_DIR = ROOT / "data" / "local_fulltext" / "zotero"

TAG = "ECfinder_stage2_4g"
LOCAL_API_BASE = "http://127.0.0.1:23119"
SUPPORTED_ATTACHMENT_SUFFIXES = {".pdf", ".html", ".htm", ".xhtml", ".txt", ".md", ".xml"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if "} {" in line:
                raise ValueError(f"{path}:{line_no} contains multiple JSON objects")
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_no} is not a JSON object")
            records.append(value)
    return records


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_doi(value: str) -> str:
    return value.strip().lower().removeprefix("https://doi.org/").removeprefix("doi:")


def zotero_root() -> Path:
    return Path.home() / "Zotero"


def zotero_db_path() -> Path:
    return zotero_root() / "zotero.sqlite"


def connect_zotero() -> sqlite3.Connection:
    path = zotero_db_path()
    if not path.exists():
        raise FileNotFoundError(f"Zotero database not found: {path}")
    uri = f"file:{path.as_posix()}?mode=ro&immutable=1"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def http_request(url: str, method: str = "GET", body: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 3) -> tuple[int, str]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return 0, str(exc)


def local_api_ping() -> bool:
    status, body = http_request(f"{LOCAL_API_BASE}/connector/ping")
    return status == 200 and "zotero" in body.lower()


def zotero_desktop_running() -> bool:
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Process | Where-Object { $_.ProcessName -like '*zotero*' } | Select-Object -First 1 -ExpandProperty ProcessName"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return False
    return bool(result.stdout.strip())


def find_items_by_doi(con: sqlite3.Connection, doi: str) -> list[sqlite3.Row]:
    return list(
        con.execute(
            """
            select i.itemID, i.key
            from items i
            join itemData d on d.itemID = i.itemID
            join fields f on f.fieldID = d.fieldID
            join itemDataValues v on v.valueID = d.valueID
            where lower(f.fieldName) = 'doi' and lower(v.value) = lower(?)
            order by i.itemID
            """,
            (normalize_doi(doi),),
        )
    )


def item_field(con: sqlite3.Connection, item_id: int, field_name: str) -> str:
    row = con.execute(
        """
        select v.value
        from itemData d
        join fields f on f.fieldID = d.fieldID
        join itemDataValues v on v.valueID = d.valueID
        where d.itemID = ? and f.fieldName = ?
        """,
        (item_id, field_name),
    ).fetchone()
    return str(row["value"]) if row else ""


def item_tags(con: sqlite3.Connection, item_id: int) -> list[str]:
    rows = con.execute(
        """
        select t.name
        from itemTags it
        join tags t on t.tagID = it.tagID
        where it.itemID = ?
        order by t.name
        """,
        (item_id,),
    ).fetchall()
    return [str(row["name"]) for row in rows]


def resolve_attachment_path(attachment_key: str, path_text: str) -> Path:
    if path_text.startswith("storage:"):
        return zotero_root() / "storage" / attachment_key / path_text.split(":", 1)[1]
    path = Path(path_text)
    if path.is_absolute():
        return path
    return zotero_root() / path


def attachments_for_item(con: sqlite3.Connection, item_id: int) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        select child.itemID, child.key, ia.contentType, ia.path
        from itemAttachments ia
        join items child on child.itemID = ia.itemID
        where ia.parentItemID = ?
        order by child.itemID
        """,
        (item_id,),
    ).fetchall()
    attachments: list[dict[str, Any]] = []
    for row in rows:
        resolved = resolve_attachment_path(str(row["key"]), str(row["path"] or ""))
        suffix = resolved.suffix.lower()
        supported = suffix in SUPPORTED_ATTACHMENT_SUFFIXES or str(row["contentType"] or "").lower() in {
            "application/pdf",
            "text/html",
            "application/xhtml+xml",
        }
        attachments.append(
            {
                "attachment_item_id": int(row["itemID"]),
                "attachment_key": str(row["key"]),
                "content_type": str(row["contentType"] or ""),
                "path": str(resolved),
                "exists": resolved.exists() and resolved.is_file(),
                "supported": supported,
                "bytes": resolved.stat().st_size if resolved.exists() and resolved.is_file() else 0,
            }
        )
    return attachments


def manifest_targets(path: Path = MANIFEST_PATH) -> list[dict[str, Any]]:
    return read_jsonl(path)


def zotero_snapshot(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        con = connect_zotero()
    except FileNotFoundError:
        for target in targets:
            rows.append(
                {
                    "source_id": target.get("source_id", ""),
                    "doi": target.get("doi", ""),
                    "title": target.get("title", ""),
                    "zotero_item_count": 0,
                    "zotero_item_keys": [],
                    "zotero_item_ids": [],
                    "zotero_has_stage2_4g_tag": False,
                    "attachments": [],
                }
            )
        return rows
    with con:
        for target in targets:
            matches = find_items_by_doi(con, str(target.get("doi", "")))
            attachments: list[dict[str, Any]] = []
            tags: list[str] = []
            for item in matches:
                attachments.extend(attachments_for_item(con, int(item["itemID"])))
                tags.extend(item_tags(con, int(item["itemID"])))
            rows.append(
                {
                    "source_id": target.get("source_id", ""),
                    "doi": target.get("doi", ""),
                    "title": target.get("title", ""),
                    "zotero_item_count": len(matches),
                    "zotero_item_keys": [str(item["key"]) for item in matches],
                    "zotero_item_ids": [int(item["itemID"]) for item in matches],
                    "zotero_has_stage2_4g_tag": TAG in set(tags),
                    "attachments": attachments,
                }
            )
    return rows


def capability_summary() -> dict[str, Any]:
    desktop = zotero_desktop_running()
    local_api = local_api_ping()
    root = zotero_root()
    storage = root / "storage"
    sqlite_ok = False
    sqlite_copy_ok = False
    notes: list[str] = []
    try:
        with connect_zotero() as con:
            con.execute("select count(*) from items").fetchone()
            sqlite_ok = True
        cache_copy = Path(tempfile.gettempdir()) / f"ecfinder_zotero_readonly_check_{uuid.uuid4().hex}.sqlite"
        try:
            shutil.copyfile(zotero_db_path(), cache_copy)
            with sqlite3.connect(cache_copy) as con:
                con.execute("select count(*) from items").fetchone()
                sqlite_copy_ok = True
        finally:
            try:
                cache_copy.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception as exc:  # noqa: BLE001
        notes.append(f"sqlite_read_failed: {type(exc).__name__}")
    better_bibtex = False
    if local_api:
        for endpoint in ["/better-bibtex/json-rpc", "/better-bibtex/cayw"]:
            status, _ = http_request(f"{LOCAL_API_BASE}{endpoint}", timeout=2)
            if status not in {0, 404}:
                better_bibtex = True
                break
    web_api_key = bool(os.environ.get("ZOTERO_API_KEY"))
    web_user = bool(os.environ.get("ZOTERO_USER_ID") or os.environ.get("ZOTERO_GROUP_ID"))
    web_api_available = web_api_key and web_user
    targets = manifest_targets()
    snapshot = zotero_snapshot(targets)
    existing = sum(1 for row in snapshot if row["zotero_item_count"] > 0)
    attachment_sources = sum(1 for row in snapshot if any(att["exists"] and att["supported"] for att in row["attachments"]))
    can_create = web_api_available
    return {
        "zotero_desktop_running": desktop,
        "local_api_available": local_api,
        "storage_readable": storage.exists() and os.access(storage, os.R_OK),
        "sqlite_readable_copy": sqlite_copy_ok,
        "better_bibtex_available": better_bibtex,
        "web_api_available": web_api_available,
        "can_create_items": can_create,
        "can_read_attachments": sqlite_ok and sqlite_copy_ok,
        "can_trigger_find_available_pdf": False,
        "trigger_method": None,
        "stage2_4g_tagged_items_seen": sum(1 for row in snapshot if row.get("zotero_has_stage2_4g_tag")),
        "exact_doi_items_seen": existing,
        "sources_with_supported_attachments": attachment_sources,
        "notes": "; ".join(notes) if notes else "Zotero SQLite is treated as read-only; no local programmable Find Available PDF endpoint was detected.",
    }


def parse_report_counts(path: Path) -> dict[str, str]:
    counts: dict[str, str] = {}
    if not path.exists():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        if " = " not in line:
            continue
        key, value = line.split(" = ", 1)
        if key.replace("_", "").isalnum():
            counts[key] = value
    return counts


def write_key_value_report(path: Path, title: str, values: dict[str, Any], extra_lines: list[str] | None = None) -> None:
    lines = [f"# {title}", ""]
    for key, value in values.items():
        if isinstance(value, bool):
            rendered = str(value).lower()
        elif value is None:
            rendered = "null"
        else:
            rendered = str(value)
        lines.append(f"{key} = {rendered}")
    if extra_lines:
        lines.extend(["", *extra_lines])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
