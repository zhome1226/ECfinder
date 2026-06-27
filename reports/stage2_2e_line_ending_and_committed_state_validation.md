# Stage 2.2e Line Ending and Committed State Validation

## Summary

- commit_hash = f85a1f91a5dd50e7ccb53420a84e00b41fb64a65
- clean_jsonl_records = 9
- clean_csv_rows = 9
- current_repository_commands_ok = true
- fresh_clone_commands_ok = true
- fresh_clone_git_status_short_empty = true
- validation_ok = true
- stage2_3_ready_or_not = ready_for_targeted_followup

## Current Repository Command Outputs

### normalize_text_line_endings

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python scripts/normalize_text_line_endings.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/normalize_text_line_endings.py
```

Exit code: 0

stdout:
```text
normalized_file_count 0
```

stderr:
```text
```

### rewrite_clean_jsonl_lf

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python scripts/rewrite_clean_jsonl_lf.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/rewrite_clean_jsonl_lf.py
```

Exit code: 0

stdout:
```text
clean_records_written 9
clean_jsonl data/clean/pfas_natural_transformation_records_v1.jsonl
clean_csv data/clean/pfas_natural_transformation_records_v1.csv
clean_sources data/clean/pfas_natural_transformation_sources_v1.jsonl
```

stderr:
```text
```

### verify_committed_text_integrity

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python scripts/verify_committed_text_integrity.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/verify_committed_text_integrity.py
```

Exit code: 0

stdout:
```text
text_files_checked 165
jsonl_files_checked 54
clean_jsonl_records 9
clean_csv_rows 9
no_cr_bytes true
validation_ok true
```

stderr:
```text
```

### py_compile

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python -m py_compile src/ecfinder/pipeline/*.py src/ecfinder/cli.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\__init__.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\__main__.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\contracts.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\exceptions.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\gates.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\orchestrator.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\queues.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\report.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\state.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\steps.py" "C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\cli.py"
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### pipeline_preflight

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python -m ecfinder.cli pipeline-preflight
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m ecfinder.cli pipeline-preflight
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### pipeline_validate_clean

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
python -m ecfinder.cli pipeline-validate-clean
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m ecfinder.cli pipeline-validate-clean
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### git_diff_check

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
git diff --check
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### git_status_short

Working directory:
```text
C:\Users\Administrator\Documents\pfasfinder\ECfinder
```

Command:
```text
git status --short
```

Exit code: 0

stdout:
```text
 M data/clean/pfas_natural_transformation_records_v1.csv
 M data/clean/pipeline_events.jsonl
 M data/clean/pipeline_state.json
 M data/clean/schema_clean_v1.yaml
 M data/extracted/pfas_transformation_records_codex_raw.jsonl
 M data/gold/pilot_gold_records.jsonl
 M data/interim/codex_screen_results.jsonl
 M data/reviewed/auxiliary_engineered_biological_records.csv
 M data/reviewed/pfas_transformation_records_validated.csv
 M data/reviewed/reextraction_attempts.jsonl
 M data/reviewed/stage2_pfas_transformation_records_validated.csv
 M reports/auxiliary_evidence_summary.md
 M reports/clean_database_v1_summary.md
 M reports/clean_database_v1_validation.md
 M reports/extraction_quality_audit.md
 M reports/failure_analysis.md
 M reports/legacy_stage2_output_freeze_notice.md
 M reports/manual_review_needed.md
 M reports/output_validation.md
 M reports/pilot_gold_set.md
 M reports/pipeline_contracts.md
 M reports/pipeline_preflight_report.md
 M reports/pipeline_runbook.md
 M reports/query_performance.md
 M reports/review_quality_audit.md
 M reports/stage1_5_codex_summary.md
 M reports/stage1_6_natural_environment_correction_summary.md
 M reports/stage1_7_output_validation.md
 M reports/stage1_summary.md
 M reports/stage2_1_output_fix_summary.md
 M reports/stage2_1_output_validation.md
 M reports/stage2_1b_serialization_validation.md
 M reports/stage2_1c_serialization_repair.md
 M reports/stage2_2_query_performance.md
 M reports/stage2_2_targeted_followup_summary.md
 M reports/stage2_2_validated_records_audit.md
 M reports/stage2_2b_orchestrator_diagnosis.md
 M reports/stage2_2c_execution_proof.md
 M reports/stage2_2d_fresh_clone_validation.md
 M reports/stage2_candidate_primary_studies.md
 M reports/stage2_extraction_review_summary.md
 M reports/stage2_failure_analysis.md
 M reports/stage2_followup_plan.md
 M reports/stage2_query_performance.md
 M reports/stage2_search_targets.md
 M reports/stage2_validated_records_audit.md
 M scripts/build_clean_database_v1.py
 M scripts/repair_stage2_serialization.py
 M src/ecfinder/pipeline/orchestrator.py
 M src/ecfinder/pipeline/report.py
 M src/ecfinder/pipeline/state.py
 M src/ecfinder/review/export_validated.py
 M src/ecfinder/review/rule_checks.py
?? .gitattributes
?? scripts/normalize_text_line_endings.py
?? scripts/rewrite_clean_jsonl_lf.py
?? scripts/verify_committed_text_integrity.py
```

stderr:
```text
```

## Fresh Clone Command Outputs

### git_clone

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441
```

Command:
```text
git clone --branch PFASfinder https://github.com/zhome1226/ECfinder.git
```

Exit code: 0

stdout:
```text
```

stderr:
```text
Cloning into 'ECfinder'...
```

### commit_hash

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
git rev-parse HEAD
```

Exit code: 0

stdout:
```text
f85a1f91a5dd50e7ccb53420a84e00b41fb64a65
```

stderr:
```text
```

### verify_committed_text_integrity

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
python scripts/verify_committed_text_integrity.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts/verify_committed_text_integrity.py
```

Exit code: 0

stdout:
```text
text_files_checked 161
jsonl_files_checked 50
clean_jsonl_records 9
clean_csv_rows 9
no_cr_bytes true
validation_ok true
```

stderr:
```text
```

### py_compile

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
python -m py_compile src/ecfinder/pipeline/*.py src/ecfinder/cli.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\__init__.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\__main__.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\contracts.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\exceptions.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\gates.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\orchestrator.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\queues.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\report.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\state.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\pipeline\steps.py" "C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder\src\ecfinder\cli.py"
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### pipeline_preflight

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
python -m ecfinder.cli pipeline-preflight
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m ecfinder.cli pipeline-preflight
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### pipeline_validate_clean

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
python -m ecfinder.cli pipeline-validate-clean
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m ecfinder.cli pipeline-validate-clean
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

### git_status_short

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_stage2_2e_fresh_20260627_132441\ECfinder
```

Command:
```text
git status --short
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

