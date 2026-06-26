# Pipeline Contracts

## JSONL Contract

- Each non-empty line is exactly one complete JSON object.
- Each line must parse with `json.loads(line)`.
- A line containing multiple objects, such as `} {`, fails validation.
- Objects split across true newline characters fail validation.
- Empty objects `{}` are not allowed.

## Clean Main Database Contract

- `record_id`, `source_id`, `parent_compound.name`, `product_compound.name`, `conditions.setting_type`, and `evidence_quote` must be non-empty.
- `doi` or `title` must be present.
- `transformation.reaction_type` or `transformation.reaction_description` must be non-empty.
- `review.review_status` must be one of `validated_high_confidence`, `validated_medium_confidence`, or `validated_low_confidence`.
- `review.evidence_tier` must be one of `confirmed_product`, `probable_product`, or `tentative_product`.
- `source_type` must be `primary_study` or explicitly primary evidence.

## Natural Environment Boundary

- The clean main database cannot contain activated sludge, wastewater treatment, WWTP, engineered treatment, AOP, electrochemical, plasma, ozonation, photocatalysis, hydrothermal, or incineration evidence.
- Engineered biological treatment evidence belongs in auxiliary records, not the clean main database.

## Manual Review Contract

- Uncertain records must be placed in `data/clean/manual_review_queue.jsonl`.
- Manual-review items must include `record_id`, `reason`, `blocking_fields`, `source_id`, `chunk_id`, `evidence_quote`, and `suggested_action`.

## Report Consistency Contract

- Counts in readiness reports must match real JSONL/CSV parsing results.
- If report counts disagree with files, the report-consistency gate fails and no ready report may be produced.
