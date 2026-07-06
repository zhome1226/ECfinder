# Stage 2.7 JSONL Serialization Repair Audit

targets_checked = 14
all_targets_strict_jsonl = true

| path | objects_recovered | rows | physical_lines_before | physical_lines_after | strict_one_object_per_line | status |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| data/state/stage2_7_library_source_status.jsonl | 300 | 300 | 300 | 300 | true | repaired |
| data/state/stage2_7_daemon_events.jsonl | 301 | 301 | 301 | 301 | true | repaired |
| data/state/stage2_7_blocked_external_queue.jsonl | 1 | 1 | 1 | 1 | true | repaired |
| data/state/stage2_7_manual_screen_queue.jsonl | 96 | 96 | 96 | 96 | true | repaired |
| data/state/stage2_7_deferred_queue.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/state/stage2_7_completed_sources.jsonl | 203 | 203 | 203 | 203 | true | repaired |
| data/batches/stage2_7_screening_decisions.jsonl | 300 | 300 | 300 | 300 | true | repaired |
| data/batches/stage2_7_chunk_screening.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_candidate_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_reviewed_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_validated_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_manual_review_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_rejected_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
| data/batches/stage2_7_auxiliary_records.jsonl | 0 | 0 | 0 | 0 | true | repaired |
