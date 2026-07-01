# Stage 2.6 Autonomous Workflow Design

main_entry = python scripts/run_autonomous_workflow.py --batch-id zotero_library --mode title_abstract_first --until-idle

workflow = Title/abstract screening -> selected fulltext ingest -> chunk relevance -> extraction -> immediate review -> database write

batch_id = stage2_6_smoke
mode = title_abstract_first
dry_run = true
active_skills = 12
screened_sources = 2
include_for_fulltext = 1
excluded = 1
manual_screen = 0
fulltext_ingest_executed = false
extraction_executed = false
no_runnable_tasks_remain = true
status = dry_run_passed
