# Evidence and English translations

Original evidence remains immutable. Its recorded SHA256 is authoritative. English views translate prose and retain the original measurement payload; they are not new test runs.

| Task | English reading view | Immutable original |
|---|---|---|
| FND-001 | [Foundation verification](FND-001.en.json) | [Original](FND-001.json) |
| DEV-001 | [Device inventory](DEV-001.en.json) | [Original](DEV-001.json) |
| DEV-002 | [Extended collector verification](DEV-002.en.json) | [Original](DEV-002.json) |

Each view contains `translation.source`, `source_sha256`, `translated_at` and `translation_only`. Its original `recorded_at`, outcome, commands and historical artifact hashes remain unchanged. Task and experiment entries retain the original `evidence` and `evidence_sha256`; `evidence_translation` provides the reading view.

New evidence is written directly in English. Historical hashes of maintained source or documentation describe the original tested version, not later revisions. Device evidence still requires private local inventory/artifacts that are intentionally excluded from Git.

See [the language policy](../../docs/language.md).
