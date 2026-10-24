BEGIN IMMEDIATE;

CREATE TABLE provider_projects (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    project_id TEXT NOT NULL,
    label TEXT NOT NULL,
    credential_env TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (provider, project_id)
);

CREATE TABLE provider_sync_runs (
    id TEXT PRIMARY KEY,
    provider_project_id INTEGER NOT NULL REFERENCES provider_projects(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'complete', 'failed')),
    page_count INTEGER NOT NULL DEFAULT 0,
    voice_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_class TEXT
);

CREATE TABLE voices (
    id TEXT PRIMARY KEY,
    provider_project_id INTEGER NOT NULL REFERENCES provider_projects(id),
    provider_voice_id TEXT NOT NULL,
    voice_type TEXT NOT NULL CHECK (voice_type IN ('prompted', 'replicated')),
    display_name TEXT,
    model TEXT,
    prompted_input TEXT,
    description TEXT,
    language_code TEXT,
    region_code TEXT,
    accent TEXT,
    gender TEXT,
    persona TEXT,
    context TEXT,
    pitch TEXT,
    expire_time TEXT,
    availability TEXT NOT NULL CHECK (availability IN ('available', 'unavailable')),
    preview_path TEXT,
    preview_sha256 TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_seen_run_id TEXT NOT NULL REFERENCES provider_sync_runs(id),
    UNIQUE (provider_project_id, provider_voice_id)
);

CREATE INDEX voices_project_availability ON voices(provider_project_id, availability);

CREATE TABLE voice_lineage (
    child_voice_id TEXT PRIMARY KEY REFERENCES voices(id),
    parent_voice_id TEXT REFERENCES voices(id),
    operation TEXT NOT NULL CHECK (operation IN ('import', 'new', 'regenerate', 'remix')),
    created_at TEXT NOT NULL,
    CHECK (parent_voice_id IS NULL OR parent_voice_id <> child_voice_id)
);

PRAGMA user_version = 1;
COMMIT;
