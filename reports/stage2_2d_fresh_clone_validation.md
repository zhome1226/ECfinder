# Stage 2.2d Fresh Clone Validation

## Required Fields

- fresh_clone_commit = e83b9ee6d5b5cc1c651b08f93e1beec0424cd1a7
- git_status_short = (empty)
- py_compile_exit_code = 0
- pipeline_preflight_exit_code = 0
- pipeline_validate_clean_exit_code = 0
- pipeline_status_exit_code = 0
- strict_jsonl_check_exit_code = 0
- clean_jsonl_record_count_from_fresh_clone = 9
- clean_csv_row_count_from_fresh_clone = 9
- python_file_line_counts = |
  src/ecfinder/cli.py: lines=753, chars=37944
  src/ecfinder/pipeline/gates.py: lines=368, chars=14134
  src/ecfinder/pipeline/contracts.py: lines=215, chars=8144
  src/ecfinder/pipeline/orchestrator.py: lines=264, chars=9990
  data/clean/pfas_natural_transformation_records_v1.jsonl: lines=9, chars=29860
- validation_ok = true
- stage2_3_ready_or_not = ready_for_targeted_followup

## Fresh Clone Directory

```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

## Command Outputs

### git_clone

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659
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

### git_rev_parse_head

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

Command:
```text
git rev-parse HEAD
```

Exit code: 0

stdout:
```text
e83b9ee6d5b5cc1c651b08f93e1beec0424cd1a7
```

stderr:
```text
```

### git_status_short_initial

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
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

### py_compile

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

Command:
```text
python -m py_compile src/ecfinder/pipeline/*.py src/ecfinder/cli.py
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\__init__.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\__main__.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\contracts.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\exceptions.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\gates.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\orchestrator.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\queues.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\report.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\state.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\pipeline\steps.py" "C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder\src\ecfinder\cli.py"
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
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
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
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
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

### pipeline_status

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

Command:
```text
python -m ecfinder.cli pipeline-status
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m ecfinder.cli pipeline-status
```

Exit code: 0

stdout:
```text
pipeline_version: stage2_2b_v1
run_id: run_20260627T013708Z_c96a19cc
status: completed
current_step: write_reports
last_successful_step: write_reports
active_profile: clean_validation
gate.clean_database_integrity: passed
gate.jsonl_integrity: passed
gate.natural_environment_boundary: passed
gate.preflight: passed
gate.report_consistency: passed
gate.stage_readiness: passed
confirmed_product_count: 1
csv_data_rows: 9
csv_has_header: True
error_queue_count: 0
manual_review_queue_count: 0
probable_product_count: 5
record_count: 9
requires_manual_confirmation_count: 4
source_count: 3
task_queue_count: 0
tentative_product_count: 3
```

stderr:
```text
```

### strict_jsonl_check

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

Command:
```text
python - <<'PY'
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\command_outputs\strict_jsonl_check.py
```

Exit code: 0

stdout:
```text
data/clean/pfas_natural_transformation_records_v1.jsonl 9
data/clean/pfas_natural_transformation_sources_v1.jsonl 3
data/clean/pfas_natural_transformation_rejected_v1.jsonl 0
data/clean/pfas_natural_transformation_manual_review_v1.jsonl 0
data/clean/pfas_auxiliary_engineered_biological_v1.jsonl 0
data/clean/manual_review_queue.jsonl 0
data/clean/task_queue.jsonl 0
data/clean/error_queue.jsonl 0
clean_csv_rows 9
```

stderr:
```text
```

### python_file_line_counts

Working directory:
```text
C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\ECfinder
```

Command:
```text
python - <<'PY'
```

Executed command:
```text
C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe C:\Users\Administrator\Documents\ecfinder_fresh_validation_20260627_093659\command_outputs\line_count_check.py
```

Exit code: 0

stdout:
```text
src/ecfinder/cli.py: lines=753, chars=37944
src/ecfinder/pipeline/gates.py: lines=368, chars=14134
src/ecfinder/pipeline/contracts.py: lines=215, chars=8144
src/ecfinder/pipeline/orchestrator.py: lines=264, chars=9990
data/clean/pfas_natural_transformation_records_v1.jsonl: lines=9, chars=29860
```

stderr:
```text
```

