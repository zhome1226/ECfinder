# Pipeline Runbook

## Standard Commands

```bash
python -m ecfinder.cli pipeline-preflight
python -m ecfinder.cli pipeline-status
python -m ecfinder.cli pipeline-run-targeted --max-sources 10
```

## Gate Rules

- If `pipeline-preflight` fails, stop. Do not search, merge, or write a ready report.
- Inspect `data/clean/error_queue.jsonl` and `reports/pipeline_preflight_report.md` for the exact failed gate and file-level reason.
- Re-run `python -m ecfinder.cli pipeline-preflight` after repairing the cause.

## Manual Review Queue

- Pending uncertain records belong in `data/clean/manual_review_queue.jsonl`.
- Codex should read each queue item, inspect the referenced source/chunk, and choose `reextract`, `manual_check_full_text`, `reject`, or `promote_after_confirmation`.
- A record should not enter `pfas_natural_transformation_records_v1.jsonl` until the blocking fields are resolved and gates pass.

## Error Queue

- `data/clean/error_queue.jsonl` contains current blocking errors from the most recent failed run.
- Fix the underlying file or report mismatch, then rerun preflight. A passing run clears the queue.

## Stage Decisions

- Stage 2.3 targeted follow-up is allowed only when all hard gates pass and the clean database remains the source of truth.
- Stage 3 broad synthesis is not allowed merely because preflight passes; it requires broader source coverage, multiple parent classes, and enough validated records for synthesis.
