"""Command-line entry point for the local Master Voice Library."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .catalog import (assignment_history, catalog_summary, character_details,
                      list_characters, list_voices, voice_details)
from .db import (DEFAULT_DB, PROVIDER, configure_project, database,
                 initialize_database, project_by_id)
from .management import (add_tag, annotate_voice,
                         archive_assignment, assign_voice, create_character,
                         create_scope, max_active_assignments, prefer_assignment,
                         restore_assignment, scope_id_for, set_max_active_assignments,
                         set_tag, update_character)
from .providers import FixtureVoicesAdapter, GoogleVoicesAdapter
from .sync import SyncError, sync_project


def _tags_parser(parent: argparse.ArgumentParser, entity: str) -> None:
    tags = parent.add_parser("tag", help=f"Attach or detach a {entity} tag")
    actions = tags.add_subparsers(dest="tag_action", required=True)
    for name in ("add", "remove"):
        action = actions.add_parser(name)
        action.add_argument("--catalog-id" if entity == "voice" else "--character-id", required=True)
        action.add_argument("--tag", required=True)


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Local Master Voice Library")
    cli.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite catalog path")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Create or explicitly migrate the local database")

    projects = commands.add_parser("projects", help="Configure or list project identities")
    project_commands = projects.add_subparsers(dest="action", required=True)
    add = project_commands.add_parser("add")
    add.add_argument("--project-id", required=True)
    add.add_argument("--label", required=True)
    add.add_argument("--credential-env", required=True,
                     help="Environment variable name; the credential value is never stored")
    project_commands.add_parser("list")

    scopes = commands.add_parser("scopes", help="Manage character identity scopes")
    scope_commands = scopes.add_subparsers(dest="action", required=True)
    scope_add = scope_commands.add_parser("add")
    scope_add.add_argument("--kind", required=True, choices=("library", "series", "universe", "book"))
    scope_add.add_argument("--key", required=True)
    scope_add.add_argument("--name", required=True)
    scope_commands.add_parser("list")

    characters = commands.add_parser("characters", help="Manage local characters")
    character_commands = characters.add_subparsers(dest="action", required=True)
    character_add = character_commands.add_parser("add")
    character_add.add_argument("--name", required=True)
    character_add.add_argument("--scope-kind", default="library")
    character_add.add_argument("--scope-key", default="default")
    character_add.add_argument("--description")
    character_add.add_argument("--notes")
    character_list = character_commands.add_parser("list")
    character_list.add_argument("--scope-kind")
    character_list.add_argument("--scope-key")
    character_show = character_commands.add_parser("show")
    character_show.add_argument("--character-id", required=True)
    character_edit = character_commands.add_parser("edit")
    character_edit.add_argument("--character-id", required=True)
    character_edit.add_argument("--name")
    character_edit.add_argument("--description")
    character_edit.add_argument("--notes")
    _tags_parser(character_commands, "character")

    voices = commands.add_parser("voices", help="Inspect and annotate local voice records")
    voice_commands = voices.add_subparsers(dest="action", required=True)
    voice_list = voice_commands.add_parser("list")
    voice_list.add_argument("--project-id")
    voice_list.add_argument("--provider")
    voice_show = voice_commands.add_parser("show")
    voice_show.add_argument("--project-id", required=True)
    voice_show.add_argument("--voice-id", required=True, help="Provider voice ID")
    voice_show.add_argument("--provider", default=PROVIDER)
    voice_summary = voice_commands.add_parser("summary")
    voice_summary.add_argument("--project-id")
    voice_summary.add_argument("--provider")
    voice_annotate = voice_commands.add_parser("annotate")
    voice_annotate.add_argument("--catalog-id", required=True, help="Stable local voice ID from voices list")
    voice_annotate.add_argument("--name")
    voice_annotate.add_argument("--description")
    voice_annotate.add_argument("--notes")
    _tags_parser(voice_commands, "voice")

    tags = commands.add_parser("tags", help="Inspect or add reusable local tags")
    tag_commands = tags.add_subparsers(dest="action", required=True)
    tag_add = tag_commands.add_parser("add")
    tag_add.add_argument("--name", required=True)
    tag_commands.add_parser("list")

    assignments = commands.add_parser("assignments", help="Manage character voice candidates")
    assignment_commands = assignments.add_subparsers(dest="action", required=True)
    assignment_add = assignment_commands.add_parser("add")
    assignment_add.add_argument("--character-id", required=True)
    assignment_add.add_argument("--catalog-id", required=True, help="Stable local voice ID from voices list")
    assignment_add.add_argument("--slot", type=int)
    assignment_add.add_argument("--role")
    assignment_add.add_argument("--notes")
    for action in ("list", "history"):
        entry = assignment_commands.add_parser(action)
        entry.add_argument("--character-id", required=True)
    assignment_prefer = assignment_commands.add_parser("prefer")
    assignment_prefer.add_argument("--assignment-id", required=True)
    assignment_archive = assignment_commands.add_parser("archive")
    assignment_archive.add_argument("--assignment-id", required=True)
    assignment_archive.add_argument("--next-preferred", help="Required when archiving a preferred voice with alternatives")
    assignment_restore = assignment_commands.add_parser("restore")
    assignment_restore.add_argument("--assignment-id", required=True, help="Archived assignment ID")
    assignment_restore.add_argument("--slot", type=int)

    settings = commands.add_parser("settings", help="Inspect or change catalog limits")
    setting_commands = settings.add_subparsers(dest="action", required=True)
    setting_commands.add_parser("show")
    setting_set = setting_commands.add_parser("set-max-active")
    setting_set.add_argument("--value", required=True, type=int)

    sync = commands.add_parser("sync", help="Scan and reconcile one Google project")
    sync.add_argument("--project-id", required=True)
    sync.add_argument("--page-size", type=int, default=100)
    mode = sync.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixture", type=Path, help="Offline JSON fixture; never opens a network client")
    mode.add_argument("--live", action="store_true", help="Explicitly use the live read-only Google API")
    return cli


def _readonly(args: argparse.Namespace) -> bool:
    return ((args.command == "projects" and args.action == "list")
            or (args.command == "scopes" and args.action == "list")
            or (args.command == "characters" and args.action in {"list", "show"})
            or (args.command == "voices" and args.action in {"list", "show", "summary"})
            or (args.command == "tags" and args.action == "list")
            or (args.command == "assignments" and args.action in {"list", "history"})
            or (args.command == "settings" and args.action == "show"))


def _updates(args: argparse.Namespace, fields: tuple[str, ...]) -> dict:
    return {field: getattr(args, field) for field in fields if getattr(args, field) is not None}


def _print(value: object) -> None:
    print(json.dumps(value, indent=2))


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            version, backup = initialize_database(args.db)
            print(f"Initialized schema version {version} at {args.db}")
            if backup:
                print(f"Verified pre-migration backup: {backup}")
            return 0

        with database(args.db, readonly=_readonly(args)) as conn:
            if args.command == "projects":
                if args.action == "add":
                    configure_project(conn, args.project_id, args.label, args.credential_env)
                    print(f"Configured {PROVIDER} project {args.project_id}")
                else:
                    _print([dict(row) for row in conn.execute(
                        "SELECT provider, project_id, label, credential_env FROM provider_projects ORDER BY project_id"
                    )])
            elif args.command == "scopes":
                if args.action == "add":
                    _print({"scope_id": create_scope(conn, args.kind, args.key, args.name)})
                else:
                    _print([dict(row) for row in conn.execute(
                        "SELECT id, kind, scope_key, display_name FROM character_scopes ORDER BY kind, scope_key"
                    )])
            elif args.command == "characters":
                if args.action == "add":
                    scope_id = scope_id_for(conn, args.scope_kind, args.scope_key)
                    _print({"character_id": create_character(
                        conn, scope_id, args.name, args.description, args.notes)})
                elif args.action == "list":
                    if bool(args.scope_kind) != bool(args.scope_key):
                        raise ValueError("Supply both --scope-kind and --scope-key")
                    scope_id = scope_id_for(conn, args.scope_kind, args.scope_key) if args.scope_kind else None
                    _print(list_characters(conn, scope_id))
                elif args.action == "show":
                    _print(character_details(conn, args.character_id))
                elif args.action == "edit":
                    update_character(conn, args.character_id,
                                     **_updates(args, ("name", "description", "notes")))
                    print("Character updated")
                else:
                    set_tag(conn, "character", args.character_id, args.tag,
                            attached=args.tag_action == "add")
                    print("Character tags updated")
            elif args.command == "voices":
                if args.action == "list":
                    _print(list_voices(conn, args.project_id, provider=args.provider))
                elif args.action == "show":
                    _print(voice_details(conn, args.project_id, args.voice_id,
                                         provider=args.provider))
                elif args.action == "summary":
                    print(catalog_summary(conn, args.project_id, provider=args.provider))
                elif args.action == "annotate":
                    annotate_voice(conn, args.catalog_id,
                                   **_updates(args, ("name", "description", "notes")))
                    print("Voice annotation updated")
                else:
                    set_tag(conn, "voice", args.catalog_id, args.tag,
                            attached=args.tag_action == "add")
                    print("Voice tags updated")
            elif args.command == "tags":
                if args.action == "add":
                    _print({"tag_id": add_tag(conn, args.name)})
                else:
                    _print([dict(row) for row in conn.execute(
                        "SELECT id, name FROM tags ORDER BY name_key"
                    )])
            elif args.command == "assignments":
                if args.action == "add":
                    _print({"assignment_id": assign_voice(
                        conn, args.character_id, args.catalog_id,
                        slot=args.slot, role=args.role, notes=args.notes)})
                elif args.action in {"list", "history"}:
                    character_details(conn, args.character_id)
                    _print(assignment_history(conn, args.character_id,
                                              active_only=args.action == "list"))
                elif args.action == "prefer":
                    prefer_assignment(conn, args.assignment_id)
                    print("Preferred assignment updated")
                elif args.action == "archive":
                    archive_assignment(conn, args.assignment_id,
                                       next_preferred_id=args.next_preferred)
                    print("Assignment archived")
                else:
                    _print({"assignment_id": restore_assignment(
                        conn, args.assignment_id, slot=args.slot)})
            elif args.command == "settings":
                if args.action == "show":
                    _print({"max_active_assignments": max_active_assignments(conn)})
                else:
                    set_max_active_assignments(conn, args.value)
                    _print({"max_active_assignments": max_active_assignments(conn)})
            elif args.command == "sync":
                project = project_by_id(conn, args.project_id)
                if args.fixture:
                    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
                    result = sync_project(conn, args.project_id,
                                          FixtureVoicesAdapter(fixture), args.page_size)
                else:
                    with GoogleVoicesAdapter(project["credential_env"]) as provider:
                        result = sync_project(conn, args.project_id, provider, args.page_size)
                _print(result)
        return 0
    except (ValueError, RuntimeError, OSError, sqlite3.Error, SyncError, json.JSONDecodeError) as exc:
        # Provider exception text may contain request details or credentials.
        message = str(exc) if isinstance(exc, (ValueError, RuntimeError, SyncError)) else type(exc).__name__
        print(f"Master Voice Library: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
