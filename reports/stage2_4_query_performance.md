# Stage 2.4 Query Performance

| query_family | sources | metadata_success | download_success | parsed_sources | candidate_records | validated_records | manual_review_records | main_failure_reason | next_action |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| C2 | 11 | 11 | 0 | 1 | 4 | 4 | 0 | No lawful downloadable full text or existing local cache was available. | manual_full_text_check, use run-local validated records for audit; do not merge automatically |
| D2 | 4 | 4 | 0 | 0 | 0 | 0 | 0 | A publisher, DOI, or cache HTML/PDF response was reachable, but automatic parsing found no PFAS-relevant full-text chunks. Treating this source as metadata-only until lawful full-text content is manually confirmed. | manual_full_text_check |
| E2 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | A publisher, DOI, or cache HTML/PDF response was reachable, but automatic parsing found no PFAS-relevant full-text chunks. Treating this source as metadata-only until lawful full-text content is manually confirmed. | manual_full_text_check |
| F2 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | A publisher, DOI, or cache HTML/PDF response was reachable, but automatic parsing found no PFAS-relevant full-text chunks. Treating this source as metadata-only until lawful full-text content is manually confirmed. | manual_full_text_check |
