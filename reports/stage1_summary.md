# Stage 1 Summary

| Artifact | Records |
|---|---:|
| `data/interim/search_results.jsonl` | 12 |
| `data/interim/screened_sources.jsonl` | 12 |
| `data/interim/download_status.jsonl` | 8 |
| `data/interim/parsed_sections.jsonl` | 0 |
| `data/interim/chunks.jsonl` | 0 |
| `data/extracted/pfas_transformation_records_raw.jsonl` | 0 |
| `data/reviewed/pfas_transformation_records_validated.jsonl` | 0 |
| `data/reviewed/rejected_records.jsonl` | 0 |

## Pilot Status

- Screening decisions: `{"exclude": 4, "include": 8}`
- Download dry-run candidates: `{"dry_run:landing": 5, "dry_run:pdf": 3}`
- Raw files present outside `.gitkeep`: 0
- No copyrighted PDF or publisher HTML is committed.
- LLM extraction is scaffolded but not executed because no LLM runtime is configured in this repository.
- Full-text parsing and chunking remain empty until lawful full text is acquired.
