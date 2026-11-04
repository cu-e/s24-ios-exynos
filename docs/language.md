# Project language

English is the default working language, as requested by the owner on 2026-11-05. Use it for maintained documentation, agent instructions, task/source descriptions, code comments, CLI output, handoffs and new reports/evidence. The owner may be addressed in Russian unless they request otherwise.

Keep identifiers, commands, filenames, URLs, full SHAs, numeric observations, versions, evidence categories and authorization boundaries exact. Translate prose; do not transliterate technical identifiers or infer additional facts.

## Historical records

Original recorded evidence, device captures, logs and imported upstream/archive material retain their original bytes and language. Do not rewrite them or recompute their historical hashes merely for translation.

English evidence views use `state/evidence/ID.en.json`. Each retains the original technical payload and identifies its source, source SHA256, translation timestamp and translation-only status. The registry keeps its original evidence path/hash and links the English view through `evidence_translation`. A translation is not a new experiment or phone observation. See the [evidence index](../state/evidence/README.md).

The private English phone report is `devices/local-2026-11-05-session1.en.md`. The original `.md` report remains intact because historical evidence hashes refer to it. Raw profiles are already mostly English and are not recollected for this migration.

Maintained research notes and procedures can be translated in place. Their old contents and historical hashes remain attributable to the original Git revision; these historical hashes are not current-file checksums. For this migration, the source revision is `70f32ee` by abbreviation; use the exact full revision recorded in DOC-001 evidence. No historic outcome or device value changes.

## Resuming work

Read README.md, AGENTS.md, current CLI status, the selected task and its handoff. Prefer maintained English notes and linked translations when reading older evidence. Preserve distinctions between user reports, upstream claims, host tests and actual device measurements.
