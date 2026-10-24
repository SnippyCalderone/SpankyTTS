# Master Voice Library — M0C

This standalone Python package catalogs provider voices and manages local
characters, annotations, tags, and voice assignments. It does not change
Android, the backend, or narration experiments. The development catalog's
first M0B live, read-only Google sync completed with **16 imported voices,
zero duplicates, one page**. M0C adds local management without a provider
request or voice generation.

## Next development priority — M0D

M0D.1 is planned next: spoiler-aware OpenAI character research or manual entry,
optional analysis of user-provided EPUB content, cited editable dossiers,
provider-neutral vocal traits, Gemini-specific voice-design descriptions, and
three distinct initial prompt drafts. Check existing approved voices and their
provider IDs before proposing new generation. M0D.1 does not create voices,
audition audio, or change preferred assignments. Paid research needs explicit
user authorization. Save results and citations locally for reuse; ordinary
dossier viewing or editing, prompt compilation, and offline tests make no API
calls.

M0D.2 will create explicitly approved persistent voices with Gemini 3.8 Flash TTS and
register their provider IDs, metadata, and history without losing prior voices.
M0D.3 will audition up to three active candidates with consistent dialogue,
retain revisions and listening notes, require explicit approval for regeneration,
and select a preferred assignment explicitly. M0D.4 can begin with short,
manually attributed dialogue and controlled chapter excerpts outside
Android and NeoReader. The existing catalog supports up to three active
assignments but has no research dossiers, prompt compiler, creation client, or
audition workflow yet. The future schema should allow multiple voice variants
without implementing automated character evolution now.

Automated dialogue attribution, scene-level voice switching, and full-book
character mapping are deferred beyond the initial M0D.4 experiments.

Ashdrinker is a planned illustrative character with an end-of-first-book
spoiler cutoff. The existing 16 synchronized Gemini voices and Gabriel de
León's preferred assignment remain the catalog baseline. The current live
BOOX path still uses OpenAI `gpt-4o-mini-tts`; production character playback
requires later verified alignment and exact-request cached delivery.

M0A established the SQLite catalog and stable project-scoped voice identities;
M0B registered the owning Google Gemini project and synchronized its voices;
M0C added local character and voice management. Before the version 1 to 2
migration, verified SQLite backups were created. All 16 voice rows and their
provider metadata remained unchanged after migration.

Use the repository-root `.venv` in PowerShell from the repository root. The
only direct third-party dependency is `google-genai==2.31.0` in
`requirements.txt`; offline management and tests use the Python standard
library. The separate `experiments/gemini_tts/.venv` remains independent.

## Database and migration

The default database is the Git-ignored
`master_voice_library/data/library.sqlite3`. Run `init` explicitly to create
or migrate it:

```powershell
.\.venv\Scripts\python.exe -m master_voice_library init
.\.venv\Scripts\python.exe -m master_voice_library projects list
.\.venv\Scripts\python.exe -m master_voice_library voices summary
.\.venv\Scripts\python.exe -m master_voice_library voices list
```

Read-only CLI commands open SQLite in read-only mode and **never migrate**.
Other commands also require the current schema; if the catalog is older, run
`init`. An `init` migration of an existing older database first makes a
timestamped SQLite backup beside it and verifies integrity, foreign keys,
and provider-qualified voice identities. The migration is transactional.
Use `--db PATH` before the subcommand to select another database.

Version 2 adds scoped characters, local voice annotations, tags, assignment
history, and a configurable assignment limit. Version 1 provider projects,
sync runs, voices, and lineage remain intact. Provider metadata stays in
`voices`; user edits live in separate tables and survive synchronization.
The stable voice identity is `(provider, project_id, provider_voice_id)`;
the `catalog_id` shown by `voices list` is the stable local voice ID used for
annotations and assignments.

## Verified local assignment

The ignored development catalog contains the `empire-of-the-vampire` series
scope (**Empire of the Vampire**) and **Gabriel de León** as a character.
Gemini voice **“Gabriel de León 2”** is his active slot 1 assignment, role
`character`, and preferred voice. Confirm it without a provider request:

```powershell
.\.venv\Scripts\python.exe -m master_voice_library scopes list
.\.venv\Scripts\python.exe -m master_voice_library characters list --scope-kind series --scope-key empire-of-the-vampire
.\.venv\Scripts\python.exe -m master_voice_library voices summary
```

The SQLite catalog, its backups, and this assignment are **local Git-ignored
state**. A commit publishes the schema and commands, not the 16 imported rows
or Gabriel's assignment. The Narrator Lab and Android/NeoReader paths do not
load this assignment yet. Ashdrinker refinement and assignment, further
characters, and an optional preview/comparison interface remain pending.

## Local management examples

These commands illustrate creating a separate example series scope. Commands
that create or edit records affect only the selected local SQLite catalog.

```powershell
.\.venv\Scripts\python.exe -m master_voice_library scopes list
.\.venv\Scripts\python.exe -m master_voice_library scopes add --kind series --key example-series --name "Example series"
.\.venv\Scripts\python.exe -m master_voice_library characters add --scope-kind series --scope-key example-series --name "Mara"
.\.venv\Scripts\python.exe -m master_voice_library characters list --scope-kind series --scope-key example-series
.\.venv\Scripts\python.exe -m master_voice_library settings show
.\.venv\Scripts\python.exe -m master_voice_library settings set-max-active --value 2
```

Copy the IDs returned by `characters add`, `voices list`, and `assignments add`
into PowerShell variables before the following commands:

```powershell
$characterId = 'copy-character-id-here'
$catalogId = 'copy-catalog-id-here'
$assignmentId = 'copy-assignment-id-here'

.\.venv\Scripts\python.exe -m master_voice_library voices annotate --catalog-id $catalogId --name "Warm narrator" --description "My local voice description" --notes "Private production note"
.\.venv\Scripts\python.exe -m master_voice_library voices tag add --catalog-id $catalogId --tag warm
.\.venv\Scripts\python.exe -m master_voice_library characters edit --character-id $characterId --description "Local character description" --notes "Production note"
.\.venv\Scripts\python.exe -m master_voice_library characters tag add --character-id $characterId --tag lead
.\.venv\Scripts\python.exe -m master_voice_library assignments add --character-id $characterId --catalog-id $catalogId --slot 1 --role dialogue
.\.venv\Scripts\python.exe -m master_voice_library assignments list --character-id $characterId
.\.venv\Scripts\python.exe -m master_voice_library assignments history --character-id $characterId
.\.venv\Scripts\python.exe -m master_voice_library assignments prefer --assignment-id $assignmentId
```

`settings set-max-active` accepts 1 through 3; the default is 3. The first
active assignment becomes preferred. Other candidates require an explicit
`assignments prefer` command to change preference. Archiving a preferred
assignment with alternatives requires `--next-preferred` with another active
assignment ID. `assignments restore --assignment-id $assignmentId` creates
a new assignment linked to the archived row, leaving history intact. Optional
roles are local labels such as `narration` or `dialogue`.

`voices list`, `voices show`, assignment views, and `voices summary` report
provider availability and expiration warnings. A passed reported expiration
does not delete an assignment or automatically change the preferred voice.
The summary counts expirations within 30 days and past reported expiration.

## Synchronization and credentials

Fixture sync is offline. Use a separate database for experiments so a fixture
scan cannot mark real project voices unavailable:

```powershell
$fixtureDb = 'master_voice_library\data\fixture_catalog.sqlite3'
.\.venv\Scripts\python.exe -m master_voice_library --db $fixtureDb init
.\.venv\Scripts\python.exe -m master_voice_library --db $fixtureDb projects add --project-id fixture-project --label "Fixture project" --credential-env GEMINI_API_KEY_FIXTURE
.\.venv\Scripts\python.exe -m master_voice_library --db $fixtureDb sync --project-id fixture-project --fixture master_voice_library\fixtures\sample_voices.json
.\.venv\Scripts\python.exe -m master_voice_library --db $fixtureDb voices summary
```

Live sync still requires the explicit `sync --project-id <registered-id>
--live` command. The Google adapter uses only `voices.list` for sync and
exposes `voices.get` for read-only metadata retrieval. It has no create,
delete, update, remix, or audio-generation operation. Credentials are read
from the configured environment variable; SQLite stores only that variable's
name. A failed or incomplete scan changes no catalog voice. A successful
complete scan can mark missing provider voices unavailable while retaining
their local IDs, annotations, lineage, and assignments.

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s master_voice_library\tests -v
```

Tests use temporary databases and mocked or fixture provider responses. To
run the additional migration test against a copy of the original 16-voice
version 1 catalog, set `M0C_V1_CATALOG` to the path of its verified pre-M0C
backup before running the suite. The test never migrates that backup in place.
