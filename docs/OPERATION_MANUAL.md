# Operation Manual

This manual is for running and validating the ECfinder autonomous PFAS literature workflow on the local Zotero-backed metadata library.

## Before Running

Check the active branch and local changes:

```powershell
git branch --show-current
git status --short
```

Do not commit temporary local repair files such as `LOCAL_REPAIR_INSTRUCTIONS.md`. Do not commit PDF, HTML, SI, Zotero storage, or SQLite files.

## Controlled Production Daemon Run

Use the controlled Stage 2.7 command first:

```powershell
python scripts/run_production_autonomous_daemon.py `
  --library zotero `
  --mode title_abstract_to_database `
  --until-library-exhausted `
  --checkpoint-every 25 `
  --rescan-zotero-attachments-every-cycle `
  --max-wall-minutes 120 `
  --max-new-screen 300 `
  --max-new-fulltext 80 `
  --max-new-extract-sources 40 `
  --safe-stop-on-token-budget `
  --token-budget 250000
```

The daemon writes progress to `data/state/stage2_7_daemon_checkpoint.json` and audit reports under `reports/stage2_7_*`.

## Stop And Resume

To request a safe stop, create:

```powershell
New-Item -ItemType File -Force data/state/STOP_DAEMON
```

The daemon stops after the active source cycle completes. Remove the file before resuming:

```powershell
Remove-Item data/state/STOP_DAEMON
python scripts/run_production_autonomous_daemon.py `
  --library zotero `
  --mode title_abstract_to_database `
  --resume `
  --until-library-exhausted
```

## Validation Checklist

Compile changed Python files:

```powershell
python -m py_compile `
  scripts/run_production_autonomous_daemon.py `
  scripts/validate_stage2_7_production_daemon.py `
  src/ecfinder/orchestration/*.py `
  src/ecfinder/skills/*.py
```

Then run:

```powershell
python scripts/validate_stage2_7_production_daemon.py
python scripts/validate_stage2_6f_environment_priority_streaming.py
python scripts/validate_stage2_6e_attachment_priority_streaming.py
python scripts/validate_stage2_6d_streaming_workflow.py
python scripts/validate_stage2_6c_streaming_workflow.py
python scripts/validate_stage2_6_skill_architecture.py
python scripts/validate_state_cache_layer.py
python scripts/validate_supervisor_workflow.py
git diff --check
```

## JSONL Repair Principle

If a JSONL file is ever suspected to contain raw line breaks inside an object, do not trust line-based parsing. Recover records from the full blob with `json.JSONDecoder().raw_decode`, recursively normalize strings to remove raw CR/LF, then rewrite one object per physical line with sorted keys.

## Readiness

`ready_for_unattended_long_run = true` requires:

- daemon loop ran more than one source cycle;
- checkpoint count is at least one;
- no unreviewed candidates remain;
- pending task count is zero;
- strict JSONL audit passed;
- no long-context, fulltext-context, duplicate-work, or natural-boundary violations were found.
