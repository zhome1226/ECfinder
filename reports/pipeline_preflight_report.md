# Pipeline Preflight Report

- pipeline_version = stage2_2b_v1
- run_id = run_20260627T051843Z_1a26c6e7
- profile = clean_validation
- status = completed
- validation_ok = true
- stage2_3_ready_or_not = ready_for_targeted_followup

## Real File Counts

- confirmed_product_count = 1
- csv_data_rows = 9
- csv_has_header = True
- error_queue_count = 0
- manual_review_queue_count = 0
- probable_product_count = 5
- record_count = 9
- requires_manual_confirmation_count = 4
- source_count = 3
- task_queue_count = 0
- tentative_product_count = 3

## Gates

- preflight = passed
  - preflight.required_paths_checked = 5
- jsonl_integrity = passed
  - jsonl_integrity.error_queue.jsonl_count = 0
  - jsonl_integrity.manual_review_queue.jsonl_count = 0
  - jsonl_integrity.pfas_auxiliary_engineered_biological_v1.jsonl_count = 0
  - jsonl_integrity.pfas_natural_transformation_manual_review_v1.jsonl_count = 0
  - jsonl_integrity.pfas_natural_transformation_records_v1.jsonl_count = 9
  - jsonl_integrity.pfas_natural_transformation_rejected_v1.jsonl_count = 0
  - jsonl_integrity.pfas_natural_transformation_sources_v1.jsonl_count = 3
  - jsonl_integrity.task_queue.jsonl_count = 0
- clean_database_integrity = passed
  - clean_database_integrity.confirmed_product_count = 1
  - clean_database_integrity.csv_data_rows = 9
  - clean_database_integrity.duplicate_record_count = 0
  - clean_database_integrity.probable_product_count = 5
  - clean_database_integrity.record_count = 9
  - clean_database_integrity.requires_manual_confirmation_count = 4
  - clean_database_integrity.tentative_product_count = 3
- natural_environment_boundary = passed
  - natural_environment_boundary.offending_record_count = 0
  - natural_environment_boundary.record_count = 9
- report_consistency = passed
  - report_consistency.additional_search_candidates = 13
  - report_consistency.confirmed_product_count = 1
  - report_consistency.csv_data_rows = 9
  - report_consistency.csv_has_header = True
  - report_consistency.download_success = 2
  - report_consistency.error_queue_count = 0
  - report_consistency.manual_review_queue_count = 0
  - report_consistency.new_auxiliary_records = 0
  - report_consistency.new_manual_review_records = 7
  - report_consistency.new_rejected_records = 1
  - report_consistency.new_validated_records = 5
  - report_consistency.parsed_sources = 2
  - report_consistency.priority_doi_attempts = 9
  - report_consistency.priority_doi_full_text_success = 2
  - report_consistency.probable_product_count = 5
  - report_consistency.raw_candidate_records = 5
  - report_consistency.record_count = 9
  - report_consistency.report_count_comparisons = 32
  - report_consistency.requires_manual_confirmation_count = 4
  - report_consistency.screened_sources = 13
  - report_consistency.source_count = 3
  - report_consistency.task_queue_count = 0
  - report_consistency.tentative_product_count = 3
- stage_readiness = passed
  - stage_readiness.confirmed_product_count = 1
  - stage_readiness.csv_data_rows = 9
  - stage_readiness.csv_has_header = True
  - stage_readiness.error_queue_count = 0
  - stage_readiness.manual_review_queue_count = 0
  - stage_readiness.probable_product_count = 5
  - stage_readiness.record_count = 9
  - stage_readiness.requires_manual_confirmation_count = 4
  - stage_readiness.source_count = 3
  - stage_readiness.task_queue_count = 0
  - stage_readiness.tentative_product_count = 3

## Errors

