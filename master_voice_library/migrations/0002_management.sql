BEGIN IMMEDIATE;

CREATE TABLE character_scopes (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('library', 'series', 'universe', 'book')),
    scope_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, scope_key)
);

INSERT INTO character_scopes
    (id, kind, scope_key, display_name, created_at, updated_at)
VALUES
    ('library:default', 'library', 'default', 'Local library',
     strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE characters (
    id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL REFERENCES character_scopes(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL,
    description TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (scope_id, name_key)
);

CREATE INDEX characters_scope ON characters(scope_id, name_key);

CREATE TABLE voice_annotations (
    voice_id TEXT PRIMARY KEY REFERENCES voices(id) ON DELETE RESTRICT,
    user_name TEXT,
    user_description TEXT,
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE tags (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE voice_tags (
    voice_id TEXT NOT NULL REFERENCES voices(id) ON DELETE RESTRICT,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    PRIMARY KEY (voice_id, tag_id)
);

CREATE TABLE character_tags (
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE RESTRICT,
    tag_id TEXT NOT NULL REFERENCES tags(id) ON DELETE RESTRICT,
    PRIMARY KEY (character_id, tag_id)
);

CREATE TABLE catalog_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    max_active_assignments INTEGER NOT NULL DEFAULT 3
        CHECK (max_active_assignments BETWEEN 1 AND 3)
);

INSERT INTO catalog_settings (id, max_active_assignments) VALUES (1, 3);

CREATE TABLE character_voice_assignments (
    id TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE RESTRICT,
    voice_id TEXT NOT NULL REFERENCES voices(id) ON DELETE RESTRICT,
    slot_number INTEGER NOT NULL CHECK (slot_number BETWEEN 1 AND 3),
    role TEXT,
    notes TEXT,
    is_preferred INTEGER NOT NULL DEFAULT 0 CHECK (is_preferred IN (0, 1)),
    assigned_at TEXT NOT NULL,
    archived_at TEXT,
    restored_from_id TEXT UNIQUE REFERENCES character_voice_assignments(id) ON DELETE RESTRICT,
    CHECK (archived_at IS NULL OR is_preferred = 0),
    CHECK (restored_from_id IS NULL OR restored_from_id <> id)
);

CREATE UNIQUE INDEX assignments_active_slot
    ON character_voice_assignments(character_id, slot_number)
    WHERE archived_at IS NULL;

CREATE UNIQUE INDEX assignments_active_voice
    ON character_voice_assignments(character_id, voice_id)
    WHERE archived_at IS NULL;

CREATE UNIQUE INDEX assignments_one_preferred
    ON character_voice_assignments(character_id)
    WHERE archived_at IS NULL AND is_preferred = 1;

CREATE INDEX assignments_character_history
    ON character_voice_assignments(character_id, assigned_at);

PRAGMA user_version = 2;
COMMIT;
