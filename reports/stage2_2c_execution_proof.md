# Stage 2.2c Execution Proof

This file records raw stdout and stderr from the requested local execution checks.

## py_compile

Command:
```text
python -m py_compile src/ecfinder/pipeline/*.py src/ecfinder/cli.py
```

Executed command:
```text
python -m py_compile C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\__init__.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\__main__.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\contracts.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\exceptions.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\gates.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\orchestrator.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\queues.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\report.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\state.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\pipeline\steps.py C:\Users\Administrator\Documents\pfasfinder\ECfinder\src\ecfinder\cli.py
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

## pipeline-preflight

Command:
```text
python -m ecfinder.cli pipeline-preflight
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

## pipeline-validate-clean

Command:
```text
python -m ecfinder.cli pipeline-validate-clean
```

Exit code: 0

stdout:
```text
```

stderr:
```text
```

## pipeline-status

Command:
```text
python -m ecfinder.cli pipeline-status
```

Exit code: 0

stdout:
```text
pipeline_version: stage2_2b_v1
run_id: run_20260626T084252Z_49cd20ff
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

## independent-jsonl-check

Command:
```text
python - <<'PY'
```

Executed command:
```text
Get-Content jsonl_check.py | python -
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
```

stderr:
```text
```

## Result

- validation_ok = true
- ready_for_targeted_followup = true
