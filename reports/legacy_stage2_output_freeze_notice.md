# Legacy Stage 2 Output Freeze Notice

The legacy files under `data/reviewed/stage2_*` and `data/reviewed/pfas_transformation_records_validated.*` have a history of JSONL/CSV serialization problems. They are retained as development history but are no longer used as the authoritative database for downstream statistics or Stage 3 readiness decisions.

From Stage 2.2 onward, the clean natural-environment database is maintained under `data/clean/`. New validated records, source metadata, manual-review records, rejected records, auxiliary records, validation reports, and Stage 3 readiness decisions must use `data/clean/` as the source of truth.

Do not delete the legacy reviewed outputs, but do not continue repairing them. They may be read only to recover already confirmed seed evidence.
