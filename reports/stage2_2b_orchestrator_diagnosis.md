# Stage 2.2b Orchestrator Diagnosis

## Current State

- legacy_reviewed_outputs_frozen = true
- clean_database_source_of_truth = data/clean/
- clean_summary_claimed_records = 9
- clean_jsonl_strict_parse_ok = true

## Diagnosis

- The legacy `data/reviewed/stage2_*` and `data/reviewed/pfas_transformation_records_validated.*` outputs are frozen and retained only as historical development artifacts.
- `data/clean/` is now the source of truth for validated natural-environment PFAS transformation records, source counts, review queues, and downstream readiness decisions.
- The current clean database summary claims 9 records; because of earlier serialization failures, this claim must be continuously checked against the real JSONL and CSV files.
- Before this task, the workflow still depended on manual user re-entry for audit, review, and promotion decisions between stages.
- Before this task, the project lacked one unified orchestrator with persisted state, hard validation gates, event logging, and a human-review queue.

## Gate Observation

- clean_jsonl_record_count = 9
- clean_csv_data_rows = 9
- Current clean JSONL passed strict parser during Stage 2.2b preflight.

## Required Direction

- All future readiness reports must be generated from parsed clean files, not from hand-written counts.
- Any failed gate must stop the pipeline, write `data/clean/error_queue.jsonl`, and mark `pipeline_state.status = failed`.
- Codex semantic extraction/review must be represented through handoff queues rather than a fake in-script LLM client.
