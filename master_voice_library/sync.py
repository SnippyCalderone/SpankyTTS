"""Stage a complete provider scan before committing any catalog changes."""

from __future__ import annotations

from dataclasses import asdict
import re
import sqlite3
from uuid import uuid4

from .db import project_by_id, utc_now
from .providers import ReadOnlyVoiceProvider, VoiceMetadata


VOICE_FIELDS = (
    "voice_type", "display_name", "model", "prompted_input", "description",
    "language_code", "region_code", "accent", "gender", "persona", "context",
    "pitch", "expire_time",
)
MAX_PAGES = 1000


class SyncError(Exception):
    """A scan failed without changing any catalog voice or its availability."""


def _safe_error_class(exc: Exception) -> str:
    name = type(exc).__name__
    return name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", name) else "Exception"


def sync_project(conn: sqlite3.Connection, project_id: str,
                 provider: ReadOnlyVoiceProvider, page_size: int = 100) -> dict:
    if not 1 <= page_size <= 1000:
        raise ValueError("Page size must be between 1 and 1000")
    project = project_by_id(conn, project_id)
    run_id = str(uuid4())
    started = utc_now()
    with conn:
        conn.execute(
            """INSERT INTO provider_sync_runs
               (id, provider_project_id, started_at, status) VALUES (?, ?, ?, 'running')""",
            (run_id, project["id"], started),
        )

    seen: dict[str, VoiceMetadata] = {}
    used_tokens: set[str] = set()
    token: str | None = None
    pages = 0
    duplicates = 0
    try:
        while True:
            if pages >= MAX_PAGES:
                raise ValueError("Provider scan exceeded page safety limit")
            page = provider.list_page(token, page_size)
            pages += 1
            for voice in page.voices:
                previous = seen.get(voice.provider_voice_id)
                if previous is None:
                    seen[voice.provider_voice_id] = voice
                elif previous == voice:
                    duplicates += 1
                else:
                    raise ValueError("Conflicting metadata for duplicate voice ID")
            if not page.next_page_token:
                break
            if page.next_page_token in used_tokens:
                raise ValueError("Provider repeated a page token")
            used_tokens.add(page.next_page_token)
            token = page.next_page_token

        finished = utc_now()
        with conn:
            for voice in seen.values():
                values = asdict(voice)
                voice_id = str(uuid4())
                columns = ("id", "provider_project_id", "provider_voice_id", *VOICE_FIELDS,
                           "availability", "first_seen_at", "last_seen_at", "last_seen_run_id")
                params = (voice_id, project["id"], voice.provider_voice_id,
                          *(values[key] for key in VOICE_FIELDS),
                          "available", finished, finished, run_id)
                assignments = ", ".join(
                    f"{name}=excluded.{name}" for name in (*VOICE_FIELDS, "availability", "last_seen_at", "last_seen_run_id")
                )
                conn.execute(
                    f"INSERT INTO voices ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
                    f"ON CONFLICT(provider_project_id, provider_voice_id) DO UPDATE SET {assignments}",
                    params,
                )
                row = conn.execute(
                    "SELECT id FROM voices WHERE provider_project_id=? AND provider_voice_id=?",
                    (project["id"], voice.provider_voice_id),
                ).fetchone()
                conn.execute(
                    """INSERT OR IGNORE INTO voice_lineage
                       (child_voice_id, parent_voice_id, operation, created_at)
                       VALUES (?, NULL, 'import', ?)""",
                    (row["id"], finished),
                )
            conn.execute(
                """UPDATE voices SET availability='unavailable'
                   WHERE provider_project_id=? AND last_seen_run_id<>?""",
                (project["id"], run_id),
            )
            conn.execute(
                """UPDATE provider_sync_runs SET finished_at=?, status='complete',
                   page_count=?, voice_count=?, duplicate_count=? WHERE id=?""",
                (finished, pages, len(seen), duplicates, run_id),
            )
        return {"run_id": run_id, "project_id": project_id, "status": "complete",
                "pages": pages, "voices": len(seen), "duplicates": duplicates}
    except Exception as exc:
        with conn:
            conn.execute(
                """UPDATE provider_sync_runs SET finished_at=?, status='failed',
                   page_count=?, voice_count=?, duplicate_count=?, error_class=? WHERE id=?""",
                (utc_now(), pages, len(seen), duplicates, _safe_error_class(exc), run_id),
            )
        raise SyncError("Provider scan failed; catalog voices were preserved") from exc
