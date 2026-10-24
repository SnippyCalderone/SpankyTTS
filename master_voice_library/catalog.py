"""Read-only catalog views and provider expiry diagnostics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3


def voice_warnings(availability: str, expire_time: str | None, *,
                   now: datetime | None = None, warning_days: int = 30) -> list[str]:
    warnings = ["unavailable"] if availability == "unavailable" else []
    if expire_time is None:
        warnings.append("expiration_unknown")
        return warnings
    try:
        expiration = datetime.fromisoformat(expire_time.replace("Z", "+00:00"))
        if expiration.tzinfo is None:
            raise ValueError("Expiry has no timezone")
    except ValueError:
        warnings.append("expiration_unparseable")
        return warnings
    now = now or datetime.now(timezone.utc)
    if expiration <= now:
        warnings.append("reported_expiration_passed")
    elif expiration <= now + timedelta(days=warning_days):
        warnings.append("expires_within_30_days")
    return warnings


def list_voices(conn: sqlite3.Connection, project_id: str | None = None,
                *, provider: str | None = None, now: datetime | None = None) -> list[dict]:
    query = """SELECT v.id AS catalog_id, p.provider, p.project_id,
        v.provider_voice_id, v.voice_type, v.display_name AS provider_name,
        a.user_name, v.availability, v.expire_time,
        (SELECT COUNT(*) FROM character_voice_assignments x
         WHERE x.voice_id=v.id AND x.archived_at IS NULL) AS active_assignments,
        (SELECT COUNT(*) FROM character_voice_assignments x
         WHERE x.voice_id=v.id AND x.archived_at IS NULL AND x.is_preferred=1)
         AS preferred_assignments
        FROM voices v JOIN provider_projects p ON p.id=v.provider_project_id
        LEFT JOIN voice_annotations a ON a.voice_id=v.id"""
    filters = []
    params = []
    if project_id is not None:
        filters.append("p.project_id=?")
        params.append(project_id)
    if provider is not None:
        filters.append("p.provider=?")
        params.append(provider)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY p.provider, p.project_id, COALESCE(a.user_name, v.display_name), v.provider_voice_id"
    rows = [dict(row) for row in conn.execute(query, params)]
    for row in rows:
        row["warnings"] = voice_warnings(row["availability"], row["expire_time"], now=now)
    return rows


def voice_details(conn: sqlite3.Connection, project_id: str, provider_voice_id: str,
                  *, provider: str = "google_gemini") -> dict:
    row = conn.execute(
        """SELECT v.*, p.provider, p.project_id, a.user_name,
           a.user_description, a.notes AS user_notes
           FROM voices v JOIN provider_projects p ON p.id=v.provider_project_id
           LEFT JOIN voice_annotations a ON a.voice_id=v.id
           WHERE p.provider=? AND p.project_id=? AND v.provider_voice_id=?""",
        (provider, project_id, provider_voice_id),
    ).fetchone()
    if row is None:
        raise ValueError("Voice is not in this project's local catalog")
    result = dict(row)
    result["tags"] = [item[0] for item in conn.execute(
        """SELECT t.name FROM tags t JOIN voice_tags vt ON vt.tag_id=t.id
           WHERE vt.voice_id=? ORDER BY t.name_key""", (row["id"],)
    )]
    result["warnings"] = voice_warnings(result["availability"], result["expire_time"])
    return result


def list_characters(conn: sqlite3.Connection, scope_id: str | None = None) -> list[dict]:
    query = """SELECT c.id, c.name, c.description, c.notes,
        s.kind AS scope_kind, s.scope_key, s.display_name AS scope_name,
        (SELECT COUNT(*) FROM character_voice_assignments a
         WHERE a.character_id=c.id AND a.archived_at IS NULL) AS active_assignments,
        (SELECT a.id FROM character_voice_assignments a
         WHERE a.character_id=c.id AND a.archived_at IS NULL AND a.is_preferred=1)
         AS preferred_assignment_id
        FROM characters c JOIN character_scopes s ON s.id=c.scope_id"""
    params: tuple[str, ...] = ()
    if scope_id is not None:
        query += " WHERE c.scope_id=?"
        params = (scope_id,)
    query += " ORDER BY s.kind, s.scope_key, c.name_key"
    return [dict(row) for row in conn.execute(query, params)]


def character_details(conn: sqlite3.Connection, character_id: str) -> dict:
    row = conn.execute(
        """SELECT c.*, s.kind AS scope_kind, s.scope_key,
           s.display_name AS scope_name FROM characters c
           JOIN character_scopes s ON s.id=c.scope_id WHERE c.id=?""",
        (character_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Unknown character ID")
    result = dict(row)
    result["tags"] = [item[0] for item in conn.execute(
        """SELECT t.name FROM tags t JOIN character_tags ct ON ct.tag_id=t.id
           WHERE ct.character_id=? ORDER BY t.name_key""", (character_id,)
    )]
    result["assignments"] = assignment_history(conn, character_id, active_only=True)
    return result


def assignment_history(conn: sqlite3.Connection, character_id: str,
                       *, active_only: bool = False) -> list[dict]:
    query = """SELECT a.*, v.provider_voice_id, v.display_name AS provider_name,
        v.availability, v.expire_time, p.provider, p.project_id,
        n.user_name AS voice_user_name
        FROM character_voice_assignments a JOIN voices v ON v.id=a.voice_id
        JOIN provider_projects p ON p.id=v.provider_project_id
        LEFT JOIN voice_annotations n ON n.voice_id=v.id
        WHERE a.character_id=?"""
    if active_only:
        query += " AND a.archived_at IS NULL"
    query += " ORDER BY (a.archived_at IS NOT NULL), a.slot_number, a.assigned_at, a.id"
    rows = [dict(row) for row in conn.execute(query, (character_id,))]
    for row in rows:
        row["warnings"] = voice_warnings(row["availability"], row["expire_time"])
    return rows


def catalog_summary(conn: sqlite3.Connection, project_id: str | None = None,
                    *, provider: str | None = None) -> str:
    projects = conn.execute(
        """SELECT provider, project_id, label FROM provider_projects
           WHERE (? IS NULL OR project_id=?) AND (? IS NULL OR provider=?)
           ORDER BY provider, project_id""",
        (project_id, project_id, provider, provider),
    ).fetchall()
    if project_id is not None and not projects:
        raise ValueError("Unknown project ID")
    lines = []
    for project in projects:
        voices = list_voices(conn, project["project_id"], provider=project["provider"])
        available = sum(v["availability"] == "available" for v in voices)
        unavailable = len(voices) - available
        expiring = sum("expires_within_30_days" in v["warnings"] for v in voices)
        past = sum("reported_expiration_passed" in v["warnings"] for v in voices)
        unknown = sum(any(w in v["warnings"] for w in
                          ("expiration_unknown", "expiration_unparseable")) for v in voices)
        active = sum(v["active_assignments"] for v in voices)
        preferred = sum(v["preferred_assignments"] for v in voices)
        lines.append(f"{project['label']} ({project['provider']}/{project['project_id']})")
        lines.append(f"  Voices: {len(voices)} total, {available} available, {unavailable} unavailable")
        lines.append(f"  Expiration: {past} past reported expiry, {expiring} within 30 days, {unknown} unknown")
        lines.append(f"  Assignments: {active} active, {preferred} preferred")
    return "\n".join(lines) if lines else "No provider projects configured."
