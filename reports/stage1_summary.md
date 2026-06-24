# Stage 1 Summary

| Artifact | Records |
|---|---:|
| `data/interim/search_results.jsonl` | 17 |
| `data/interim/screened_sources.jsonl` | 17 |
| `data/interim/download_status.jsonl` | 11 |
| `data/interim/parsed_sections.jsonl` | 58 |
| `data/interim/chunks.jsonl` | 94 |
| `data/extracted/pfas_transformation_records_raw.jsonl` | 13 |
| `data/reviewed/pfas_transformation_records_validated.jsonl` | 0 |
| `data/reviewed/rejected_records.jsonl` | 13 |

## Pilot Status

- Screening decisions: `{"exclude": 6, "include": 10, "maybe": 1}`
- Download/acquisition status: `{"downloaded:pdf": 3, "failed:pdf": 2, "not_attempted:html": 1, "not_attempted:landing": 5}`
- Ignored raw files present outside `.gitkeep`: 5
- No copyrighted PDF, publisher HTML, or full parsed text is committed.
- LLM extraction is scaffolded but not executed because no LLM runtime is configured in this repository.
- Parsed section and chunk files committed here are indexes with hashes, not full text.
