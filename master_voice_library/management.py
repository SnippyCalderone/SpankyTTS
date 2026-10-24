"""Local character and voice management; this module never opens a provider client."""

from __future__ import annotations

from contextlib import contextmanager
import re
import sqlite3
from typing import Iterator
from uuid import uuid4

from .db import utc_now


DEFAULT_SCOPE_ID = "library:default"
SCOPE_KINDS = {"library", "series", "universe", "book"}
KEY = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
ROLE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
UNSET = object()


@contextmanager
def _atomic(conn: sqlite3.Connection) -> Iterator[None]:
    if conn.in_transaction:
        raise RuntimeError("Finish the current database transaction before a management operation")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _required_text(value: str, label: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _name_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _exists(conn: sqlite3.Connection, table: str, entity_id: str) -> None:
    if conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (entity_id,)).fetchone() is None:
        raise ValueError(f"Unknown {table[:-1]} ID")


def create_scope(conn: sqlite3.Connection, kind: str, scope_key: str, name: str) -> str:
    kind = kind.strip().lower()
    scope_key = scope_key.strip().lower()
    if kind not in SCOPE_KINDS or not KEY.fullmatch(scope_key):
        raise ValueError("Scope requires a known kind and a lowercase slug key")
    name = _required_text(name, "Scope name")
    scope_id = str(uuid4())
    now = utc_now()
    with _atomic(conn):
        conn.execute(
            """INSERT INTO character_scopes
               (id, kind, scope_key, display_name, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (scope_id, kind, scope_key, name, now, now),
        )
    return scope_id


def scope_id_for(conn: sqlite3.Connection, kind: str, scope_key: str) -> str:
    row = conn.execute(
        "SELECT id FROM character_scopes WHERE kind=? AND scope_key=?",
        (kind.strip().lower(), scope_key.strip().lower()),
    ).fetchone()
    if row is None:
        raise ValueError("Unknown character scope")
    return row["id"]


def create_character(conn: sqlite3.Connection, scope_id: str, name: str,
                     description: str | None = None, notes: str | None = None) -> str:
    name = _required_text(name, "Character name")
    character_id = str(uuid4())
    now = utc_now()
    with _atomic(conn):
        _exists(conn, "character_scopes", scope_id)
        conn.execute(
            """INSERT INTO characters
               (id, scope_id, name, name_key, description, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (character_id, scope_id, name, _name_key(name), description, notes, now, now),
        )
    return character_id


def update_character(conn: sqlite3.Connection, character_id: str, *,
                     name: str | object = UNSET, description: str | None | object = UNSET,
                     notes: str | None | object = UNSET) -> None:
    updates: dict[str, object] = {}
    if name is not UNSET:
        updates["name"] = _required_text(name, "Character name")
        updates["name_key"] = _name_key(updates["name"])
    if description is not UNSET:
        updates["description"] = description or None
    if notes is not UNSET:
        updates["notes"] = notes or None
    if not updates:
        raise ValueError("Provide a field to update")
    updates["updated_at"] = utc_now()
    with _atomic(conn):
        _exists(conn, "characters", character_id)
        conn.execute(
            f"UPDATE characters SET {', '.join(f'{key}=?' for key in updates)} WHERE id=?",
            (*updates.values(), character_id),
        )


def annotate_voice(conn: sqlite3.Connection, voice_id: str, *,
                   name: str | None | object = UNSET,
                   description: str | None | object = UNSET,
                   notes: str | None | object = UNSET) -> None:
    updates: dict[str, object] = {}
    if name is not UNSET:
        updates["user_name"] = (name.strip() or None) if isinstance(name, str) else None
    if description is not UNSET:
        updates["user_description"] = description or None
    if notes is not UNSET:
        updates["notes"] = notes or None
    if not updates:
        raise ValueError("Provide a field to update")
    updates["updated_at"] = utc_now()
    with _atomic(conn):
        _exists(conn, "voices", voice_id)
        conn.execute(
            "INSERT OR IGNORE INTO voice_annotations (voice_id, updated_at) VALUES (?, ?)",
            (voice_id, updates["updated_at"]),
        )
        conn.execute(
            f"UPDATE voice_annotations SET {', '.join(f'{key}=?' for key in updates)} WHERE voice_id=?",
            (*updates.values(), voice_id),
        )


def add_tag(conn: sqlite3.Connection, name: str) -> str:
    name = _required_text(name, "Tag name")
    key = _name_key(name)
    with _atomic(conn):
        conn.execute(
            "INSERT OR IGNORE INTO tags (id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
            (str(uuid4()), name, key, utc_now()),
        )
        return conn.execute("SELECT id FROM tags WHERE name_key=?", (key,)).fetchone()["id"]


def set_tag(conn: sqlite3.Connection, entity: str, entity_id: str,
            tag_name: str, *, attached: bool) -> None:
    if entity not in {"voice", "character"}:
        raise ValueError("Tag target must be voice or character")
    table = "voice_tags" if entity == "voice" else "character_tags"
    id_column = "voice_id" if entity == "voice" else "character_id"
    entity_table = "voices" if entity == "voice" else "characters"
    tag_name = _required_text(tag_name, "Tag name")
    with _atomic(conn):
        _exists(conn, entity_table, entity_id)
        key = _name_key(tag_name)
        if attached:
            conn.execute(
                "INSERT OR IGNORE INTO tags (id, name, name_key, created_at) VALUES (?, ?, ?, ?)",
                (str(uuid4()), tag_name, key, utc_now()),
            )
        tag = conn.execute("SELECT id FROM tags WHERE name_key=?", (key,)).fetchone()
        if tag is None:
            raise ValueError("Unknown tag")
        if attached:
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({id_column}, tag_id) VALUES (?, ?)",
                (entity_id, tag["id"]),
            )
        else:
            conn.execute(
                f"DELETE FROM {table} WHERE {id_column}=? AND tag_id=?",
                (entity_id, tag["id"]),
            )


def max_active_assignments(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT max_active_assignments FROM catalog_settings WHERE id=1"
    ).fetchone()[0]


def set_max_active_assignments(conn: sqlite3.Connection, maximum: int) -> None:
    if not 1 <= maximum <= 3:
        raise ValueError("Maximum active assignments must be between 1 and 3")
    with _atomic(conn):
        overflow = conn.execute(
            """SELECT 1 FROM character_voice_assignments
               WHERE archived_at IS NULL AND slot_number>? LIMIT 1""", (maximum,),
        ).fetchone()
        if overflow:
            raise ValueError("Archive or move assignments in higher slots first")
        conn.execute(
            "UPDATE catalog_settings SET max_active_assignments=? WHERE id=1", (maximum,)
        )


def _active(conn: sqlite3.Connection, character_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT * FROM character_voice_assignments
           WHERE character_id=? AND archived_at IS NULL ORDER BY slot_number""",
        (character_id,),
    ).fetchall()


def _slot(rows: list[sqlite3.Row], maximum: int, requested: int | None) -> int:
    occupied = {row["slot_number"] for row in rows}
    if requested is not None:
        if not 1 <= requested <= maximum or requested in occupied:
            raise ValueError("Requested assignment slot is unavailable")
        return requested
    return next((number for number in range(1, maximum + 1) if number not in occupied), 0)


def _role(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().lower()
    if not ROLE.fullmatch(value):
        raise ValueError("Role must be a short lowercase slug")
    return value


def _assert_preference(conn: sqlite3.Connection, character_id: str) -> None:
    count, preferred = conn.execute(
        """SELECT COUNT(*), COALESCE(SUM(is_preferred), 0)
           FROM character_voice_assignments
           WHERE character_id=? AND archived_at IS NULL""",
        (character_id,),
    ).fetchone()
    if preferred != (1 if count else 0):
        raise RuntimeError("Character preference invariant failed")


def assign_voice(conn: sqlite3.Connection, character_id: str, voice_id: str, *,
                 slot: int | None = None, role: str | None = None,
                 notes: str | None = None) -> str:
    role = _role(role)
    assignment_id = str(uuid4())
    with _atomic(conn):
        _exists(conn, "characters", character_id)
        _exists(conn, "voices", voice_id)
        rows = _active(conn, character_id)
        maximum = max_active_assignments(conn)
        if len(rows) >= maximum:
            raise ValueError("Character has reached the active assignment limit")
        chosen = _slot(rows, maximum, slot)
        if not chosen:
            raise ValueError("No assignment slot is available")
        conn.execute(
            """INSERT INTO character_voice_assignments
               (id, character_id, voice_id, slot_number, role, notes, is_preferred, assigned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (assignment_id, character_id, voice_id, chosen, role, notes, int(not rows), utc_now()),
        )
        _assert_preference(conn, character_id)
    return assignment_id


def prefer_assignment(conn: sqlite3.Connection, assignment_id: str) -> None:
    with _atomic(conn):
        row = conn.execute(
            "SELECT character_id, archived_at FROM character_voice_assignments WHERE id=?",
            (assignment_id,),
        ).fetchone()
        if row is None or row["archived_at"] is not None:
            raise ValueError("Preferred assignment must be active")
        conn.execute(
            """UPDATE character_voice_assignments SET is_preferred=0
               WHERE character_id=? AND archived_at IS NULL""", (row["character_id"],),
        )
        conn.execute(
            "UPDATE character_voice_assignments SET is_preferred=1 WHERE id=?",
            (assignment_id,),
        )
        _assert_preference(conn, row["character_id"])


def archive_assignment(conn: sqlite3.Connection, assignment_id: str, *,
                       next_preferred_id: str | None = None) -> None:
    with _atomic(conn):
        row = conn.execute(
            "SELECT * FROM character_voice_assignments WHERE id=?", (assignment_id,)
        ).fetchone()
        if row is None or row["archived_at"] is not None:
            raise ValueError("Assignment is not active")
        others = [item for item in _active(conn, row["character_id"]) if item["id"] != assignment_id]
        if row["is_preferred"] and others:
            if next_preferred_id not in {item["id"] for item in others}:
                raise ValueError("Archiving the preferred voice requires --next-preferred")
        elif next_preferred_id is not None:
            raise ValueError("--next-preferred applies only when archiving a preferred voice with alternatives")
        conn.execute(
            """UPDATE character_voice_assignments
               SET archived_at=?, is_preferred=0 WHERE id=?""",
            (utc_now(), assignment_id),
        )
        if next_preferred_id:
            conn.execute(
                "UPDATE character_voice_assignments SET is_preferred=1 WHERE id=?",
                (next_preferred_id,),
            )
        _assert_preference(conn, row["character_id"])


def restore_assignment(conn: sqlite3.Connection, archived_id: str, *,
                       slot: int | None = None) -> str:
    new_id = str(uuid4())
    with _atomic(conn):
        old = conn.execute(
            "SELECT * FROM character_voice_assignments WHERE id=?", (archived_id,)
        ).fetchone()
        if old is None or old["archived_at"] is None:
            raise ValueError("Restore requires an archived assignment")
        if conn.execute(
            "SELECT 1 FROM character_voice_assignments WHERE restored_from_id=?", (archived_id,)
        ).fetchone():
            raise ValueError("This archived assignment was already restored")
        rows = _active(conn, old["character_id"])
        if len(rows) >= max_active_assignments(conn):
            raise ValueError("Character has reached the active assignment limit")
        if any(row["voice_id"] == old["voice_id"] for row in rows):
            raise ValueError("Voice is already active for this character")
        maximum = max_active_assignments(conn)
        preferred_slot = old["slot_number"] if old["slot_number"] <= maximum else None
        occupied = {row["slot_number"] for row in rows}
        chosen = _slot(rows, maximum, slot if slot is not None else
                       (preferred_slot if preferred_slot not in occupied else None))
        if not chosen:
            raise ValueError("No assignment slot is available")
        conn.execute(
            """INSERT INTO character_voice_assignments
               (id, character_id, voice_id, slot_number, role, notes, is_preferred,
                assigned_at, restored_from_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (new_id, old["character_id"], old["voice_id"], chosen, old["role"],
             old["notes"], int(not rows), utc_now(), archived_id),
        )
        _assert_preference(conn, old["character_id"])
    return new_id
