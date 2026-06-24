# Stage 2 Failure Analysis

- searched_unique_candidates: 150
- download_attempts: 47
- download_success: 29
- parsed_full_text: 14
- parsed_no_text_or_failed: 33
- rejected_records: 11
- rejection_status_counts: `{'rejected_no_transformation': 3, 'rejected_no_natural_environment': 1, 'rejected_reference_only': 1, 'rejected_insufficient_evidence': 6}`

## Main Failure Modes

- Closed or landing-page-only publisher records prevented lawful full-text parsing for several high-priority soil/sediment papers.
- Some downloaded open pages were abstracts, repository stubs, conference pages, or transport/model papers rather than primary parent-product evidence.
- Several field studies reported occurrence, transport, or precursor trends without a named parent-product transformation relationship.
- Modeling/simulation papers were kept out of the main database unless direct primary experimental evidence was present in the parsed chunk.

## Manual Full-Text Targets

- 10.1016/j.watres.2023.120941: 6:2 FTSA in AFFF-impacted soils.
- 10.1016/j.envpol.2016.01.069: PAP aerobic biotransformation in soil.
- 10.1016/j.chemosphere.2016.03.062: 6:2 FTSA in aerobic/anaerobic sediment.
- 10.1016/j.chemosphere.2014.09.059 and 10.1016/j.envpol.2017.05.074: FOSA/FOSE/PFOS precursor soil biotransformation.
- 10.1021/es0708722: 8:2 FTOH in soil and soil isolates.
