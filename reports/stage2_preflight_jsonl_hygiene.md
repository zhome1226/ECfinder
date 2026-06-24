# Stage 2 Preflight JSONL Hygiene

| Check | Result |
|---|---:|
| jsonl_parse_ok | true |
| validated_jsonl_count | 0 |
| auxiliary_jsonl_count | 8 |
| rejected_count | 16 |
| reextraction_attempt_count | 26 |
| format_issues_fixed | 0 |
| stage2_search_started_after_preflight | true |

All reviewed JSONL files were parsed with one complete JSON object per non-empty line. No embedded evidence quote newline broke the JSONL row structure, and no line contained multiple JSON objects.

`python -m ecfinder.cli validate-outputs` and `python -m ecfinder.cli audit-stage1-6` were rerun before Stage 2 search. The natural-environment validated main database remains empty, and auxiliary engineered biological evidence remains at 8 records.
