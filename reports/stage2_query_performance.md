# Stage 2 Query Performance

| query_family | search_hits | unique_candidates | screen_download | download_success | parsed_full_text | raw_records | validated_records | manual_review_records | rejected_records | most_common_rejection_reason | notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 40 | 23 | 16 | 4 | 1 | 0 | 0 | 0 | 0 |  | downloaded but no direct parent-product record validated |
| B | 40 | 10 | 5 | 3 | 3 | 0 | 0 | 0 | 2 | rejected_reference_only | downloaded but no direct parent-product record validated |
| C | 40 | 25 | 14 | 2 | 2 | 4 | 4 | 0 | 1 | rejected_no_natural_environment | validated evidence found |
| D | 40 | 21 | 11 | 7 | 5 | 0 | 0 | 1 | 4 | rejected_no_transformation | downloaded but no direct parent-product record validated |
| E | 37 | 21 | 6 | 2 | 0 | 0 | 0 | 0 | 2 | rejected_insufficient_evidence | downloaded but no direct parent-product record validated |
| F | 40 | 17 | 12 | 5 | 2 | 0 | 0 | 1 | 2 | rejected_insufficient_evidence | downloaded but no direct parent-product record validated |
| G | 39 | 19 | 10 | 5 | 1 | 0 | 0 | 0 | 0 |  | downloaded but no direct parent-product record validated |
| H | 40 | 14 | 5 | 1 | 0 | 0 | 0 | 0 | 0 |  | downloaded but no direct parent-product record validated |

## Key Metrics

- validated_records_per_downloaded_full_text: 4/14 = 0.29
- validated_records_per_query_family: `{'C': 4}`
- download_success_rate: 29/47 = 61.70%
- false_positive_reasons: `{'rejected_no_transformation': 3, 'rejected_no_natural_environment': 1, 'rejected_reference_only': 1, 'rejected_insufficient_evidence': 6}`

Best-performing family in this pilot was Query Family C because it retrieved an open primary AFFF/environmental-solids microcosm paper with directly supported products. Families D, E, and F found several high-priority primary papers, but many were closed or did not expose usable full text through lawful open channels in this run.
