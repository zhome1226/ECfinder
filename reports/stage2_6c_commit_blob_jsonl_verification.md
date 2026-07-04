# Stage 2.6c Commit Blob JSONL Verification

local_head = 08e9c15adb9714006204fea2186b28cf3c803636
fresh_clone_head = 08e9c15adb9714006204fea2186b28cf3c803636
targets = 8
all_targets_strict_jsonl = true
all_sha256_match = true
next_batch_started = false

| target | rows | physical_lines | sha256_match | first_200_repr |
| --- | ---: | ---: | --- | --- |
| data/batches/stage2_6c_streaming_candidate_records.jsonl | 1 | 1 | true | `'{"chunk_id": "stage2_4j_zotero_stage2_4j_src_006_chunk_003", "conditions": {"condition": "Gordonia sp. strain NB4-1Y pure culture under sulfur-limiting conditions", "environment_matrix": "pure culture'` |
| data/batches/stage2_6c_streaming_reviewed_records.jsonl | 1 | 1 | true | `'{"chunk_id": "stage2_4j_zotero_stage2_4j_src_006_chunk_003", "conditions": {"condition": "Gordonia sp. strain NB4-1Y pure culture under sulfur-limiting conditions", "environment_matrix": "pure culture'` |
| data/batches/stage2_6c_streaming_auxiliary_records.jsonl | 1 | 1 | true | `'{"chunk_id": "stage2_4j_zotero_stage2_4j_src_006_chunk_003", "conditions": {"condition": "Gordonia sp. strain NB4-1Y pure culture under sulfur-limiting conditions", "environment_matrix": "pure culture'` |
| data/batches/stage2_6c_streaming_rejected_records.jsonl | 1 | 1 | true | `'{"chunk_id": "stage2_4j_zotero_stage2_4j_src_033_chunk_001", "database_write_ref": "data/batches/stage2_6c_streaming_rejected_records.jsonl", "doi": "10.3390/toxics12120930", "evidence_tier": "none", '` |
| data/batches/stage2_6c_streaming_validated_records.jsonl | 0 | 0 | true | `''` |
| data/batches/stage2_6c_streaming_screening_decisions.jsonl | 100 | 100 | true | `'{"cache_hit": false, "created_at": "2026-07-01T22:50:59Z", "environment_relevance": "not_relevant", "evidence_likelihood": "unlikely", "input_fields": ["source_id", "doi", "title", "abstract", "year",'` |
| data/state/stage2_6c_streaming_source_status.jsonl | 100 | 100 | true | `'{"artifact_refs": {"screening_ref": "data/batches/stage2_6c_streaming_screening_decisions.jsonl"}, "database_write_status": "not_started", "doi": "10.1021/acs.est.3c00374", "extraction_status": "not_s'` |
| data/state/stage2_6c_streaming_events.jsonl | 114 | 114 | true | `'{"agent": "TitleAbstractScreeningAgent", "batch_id": "stage2_6c_zotero_stream", "event_id": "stage2_6c_zotero_stream_zotero_stage2_4j_src_001_screening_00001", "event_type": "skill_invoked", "fulltext'` |
