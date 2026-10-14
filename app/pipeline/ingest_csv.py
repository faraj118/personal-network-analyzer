"""CSV ingest (SPEC.md §5, §6): LinkedIn/Facebook export -> source_records.

Pure function: bytes/path in, typed SourceRecordIn list out. No DB side-effects here
(those live in db.py). Deterministic content_hash gives idempotent re-ingest (§11).
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.models.schemas import Source, SourceRecordIn

# LinkedIn Connections.csv column -> our field. Position/Company drive graph edges (§5).
_LINKEDIN_MAP = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Email Address": "email",
    "Company": "company",
    "Position": "job_title",
    "Connected On": "connected_on",
    "URL": "url",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _content_hash(source: str, mapped: dict) -> str:
    """Stable hash over source + normalized mapped fields (order-independent)."""
    norm = {k: (str(v).strip().lower() if v is not None else "") for k, v in sorted(mapped.items())}
    payload = source + "\x00" + json.dumps(norm, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _find_header_offset(text: str) -> int:
    """LinkedIn prepends a 'Notes:' preamble; the real header row has First/Last Name."""
    for i, line in enumerate(text.splitlines()):
        if "First Name" in line and "Last Name" in line:
            return i
    return 0  # already a clean header


def ingest_linkedin_csv(data: bytes | str, origin_file: str | None = None) -> list[SourceRecordIn]:
    """Map a LinkedIn Connections export into normalized source records."""
    text = data.decode("utf-8-sig") if isinstance(data, bytes) else data
    skip = _find_header_offset(text)
    df = pd.read_csv(io.StringIO(text), skiprows=skip, dtype=str).fillna("")

    records: list[SourceRecordIn] = []
    for _, row in df.iterrows():
        mapped = {
            our: str(row[col]).strip()
            for col, our in _LINKEDIN_MAP.items()
            if col in df.columns and str(row[col]).strip()
        }
        if not mapped:
            continue  # skip blank rows
        chash = _content_hash(Source.linkedin_export.value, mapped)
        records.append(
            SourceRecordIn(
                id=str(uuid.uuid4()),
                source=Source.linkedin_export,
                origin_file=origin_file,
                raw_text=json.dumps({k: str(v) for k, v in row.items()}, ensure_ascii=False),
                extracted_json=json.dumps(mapped, ensure_ascii=False),
                ingested_at=_now(),
                content_hash=chash,
            )
        )
    return records


def ingest_csv(path: Path) -> list[SourceRecordIn]:
    """Convenience: read a file path and ingest as a LinkedIn export."""
    return ingest_linkedin_csv(path.read_bytes(), origin_file=path.name)
