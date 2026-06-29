# Cache State Design

- `data/state/source_registry.jsonl` stores one source-level row per DOI/title with artifact references.
- `data/state/artifact_index.jsonl` stores reusable metadata, screening, download, chunk, extraction, and review artifacts with SHA-256 hashes.
- `data/state/decision_cache.jsonl` stores short decision references keyed by task type, input hash, prompt version, and schema version.
- `data/state/task_registry.jsonl` stores task payload paths only; long text remains in artifact files.
- `data/tasks/*.json` stores agent handoff payloads with `prompt_refs`, `schema_ref`, and input artifact references.
- `data/state/cache_stats.json` summarizes cache hits, misses, tasks created, and a conservative token-saved estimate.
