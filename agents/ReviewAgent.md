# ReviewAgent

## Purpose

Validate extracted transformation records and route weak records to rejection or re-extraction.

## Inputs

- `data/extracted/pfas_transformation_records_raw.jsonl`
- `data/interim/chunks.jsonl`
- `configs/review_rules.yaml`
- `prompts/review_transformation_records.md`
- `prompts/reextract_from_failed_chunk.md`

## Outputs

- `data/reviewed/pfas_transformation_records_validated.jsonl`
- `data/reviewed/pfas_transformation_records_validated.csv`
- `data/reviewed/rejected_records.jsonl`
- `reports/failure_analysis.md`

## Procedure

1. Run deterministic schema and provenance checks.
2. Reject records missing source, chunk, parent, product, or evidence quote.
3. Reject records unsupported by their source chunk.
4. Mark incomplete but promising chunks as `needs_reextract`.
5. Optionally call the review LLM prompt for borderline records.
6. Export accepted records to JSONL and CSV.

## Acceptance Criteria

- Accepted records are traceable to source and chunk.
- Rejections have machine-readable reasons.
- Re-extraction requests include the original `chunk_id`.
