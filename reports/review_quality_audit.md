# Review Quality Audit

## Stage 1.6 Criteria Correction

Activated sludge, wastewater treatment, WWTP bioreactors, and engineered biological treatment records are excluded from the natural-environment main database.

The eight previously validated activated-sludge records were reclassified as auxiliary_engineered_biological_evidence because activated sludge is an engineered wastewater-treatment matrix, not natural environmental transformation evidence.

## Synchronized Counts

- natural_environment_validated_count = 0
- auxiliary_engineered_biological_count = 8
- manual_review_count = 0
- rejected_count = 16
- reextraction_attempt_count = 26

| Artifact | Count |
|---|---:|
| codex raw records reviewed | 11 |
| natural-environment validated records | 0 |
| auxiliary engineered biological records | 8 |
| manual review records | 0 |
| rejected records | 16 |
| re-extraction audit attempts | 26 |

## Automated Guardrail

- engineered_terms_found_in_validated: 0
- offending_validated_record_ids: `[]`

## Rejected Status Counts

`{"rejected_insufficient_evidence": 10, "rejected_no_product": 1, "rejected_reference_only": 5}`

## Re-extraction Attempt Outcomes

`{"no_valid_record_found": 8, "original_record_rejected": 13, "yielded_records": 5}`

## Review Notes

- The 8 Stage 1.5 validated activated-sludge records were reclassified as `auxiliary_engineered_biological_evidence` because they are useful mechanistic evidence but not natural-environment evidence.
- Activated-sludge manual candidates with unclear short-chain PFCA attribution were rejected rather than promoted to auxiliary evidence.
- Review/redrawn pathway evidence was rejected as reference-only until the primary source is retrieved and reviewed.
- The main validated database is allowed to contain 0 records at this stage because the corrected corpus does not yet include primary natural-environment records that pass all criteria.
