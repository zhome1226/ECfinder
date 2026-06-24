# Stage 1.5 Codex Summary

## Execution

- Codex/GPT-5.5 used for semantic judgment: yes, via the current interactive Codex session.
- External LLM API client added: no.
- OPENAI_API_KEY required: no.
- Codex task packets prepared by CLI: 40 extraction chunk packets and 13 re-extraction packets.

## Counts

| Metric | Count |
|---|---:|
| processed_chunks | 40 |
| needs_reextract_records_reprocessed | 13 |
| codex_raw_records | 11 |
| validated_records | 8 |
| manual_review_records | 3 |
| rejected_records | 13 |
| reextraction_attempt_rows | 26 |

## Main Rejection Reasons

- Reference-list or review-derived text was rejected as non-primary evidence.
- Regex fallback merged author names, titles, and compound names.
- Several records used a parent alias as the product and had no transformation product.
- Occurrence, use inventories, adsorption, and engineered-treatment content were excluded.

## Most Credible Parent-Product Examples

- 8:2 FTOH -> perfluorooctanoic acid (aerobic, validated_high_confidence)
- 8:2 FTOH -> perfluoroheptanoic acid (aerobic, validated_high_confidence)
- 8:2 FTOH -> perfluorononanoic acid (aerobic, validated_medium_confidence)
- 8:2 FTOH -> perfluorohexanoic acid (aerobic, validated_medium_confidence)
- 8:2 FTOH -> perfluorooctanoic acid (anoxic, validated_high_confidence)
- 8:2 FTOH -> perfluorooctanoic acid (anaerobic, validated_high_confidence)

## Improvement Over Regex Fallback

Regex fallback produced 13 `needs_reextract` rows and 0 validated rows. Codex semantic review rejected the false positives and extracted 8 validated records from primary result/conclusion chunks with direct evidence quotes and environmental matrix context.

## Stage 2 Recommendation

Proceed to Stage 2 expansion only after adding more primary full text sources. The current pipeline can now validate high-confidence records, but coverage is still dominated by one original 8:2 FTOH biodegradation paper.

## Pilot Gold Set Metrics

| Metric | Count |
|---|---:|
| gold_record_count | 8 |
| extracted_match_count | 8 |
| review_validated_match_count | 8 |
| false_positive_count | 0 |
| missed_gold_count | 0 |
