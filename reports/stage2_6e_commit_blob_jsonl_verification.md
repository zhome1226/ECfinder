# Stage 2.6e Commit Blob JSONL Verification

local_head = db5773c0ae955fbc9c0fcf58d0c2002e267a49a4
fresh_clone_head = db5773c0ae955fbc9c0fcf58d0c2002e267a49a4
targets = 10
all_targets_strict_jsonl = true
all_sha256_match = true

| target | rows | physical_lines | sha256 | sha256_match | status | first_200_repr |
| --- | ---: | ---: | --- | --- | --- | --- |
| data/batches/stage2_6e_streaming_screening_decisions.jsonl | 27 | 27 | `6095977ae5da6fd37052651c5a62cd2db62026a26c8637012d25e10b2fe632cc` | true | strict_jsonl_ok | `'{"cache_hit": true, "created_at": "2026-07-04T10:33:38Z", "environment_relevance": "unclear", "evidence_likelihood": "likely_transformation_evidence", "input_fields": ["source_id", "doi", "title", "ab'` |
| data/batches/stage2_6e_streaming_chunk_screening.jsonl | 65 | 65 | `77977f2b170948f68f2bb0870e40c7695481c641feb57b88be1a99f62f6141f8` | true | strict_jsonl_ok | `'{"chunk_hash": "ca73dbb584de22750ee17af878022333fd2d4cd8c43ebf306360e44d4e517969", "chunk_id": "stage2_6e_zotero_stage2_4j_src_209_chunk_001", "created_at": "2026-07-04T10:33:38Z", "positive_hits": ["'` |
| data/batches/stage2_6e_streaming_candidate_records.jsonl | 1 | 1 | `d9f3ce91d446f43854c5c3aab7098136d7339e39a331483fc0c67a96917aa026` | true | strict_jsonl_ok | `'{"chunk_id": "stage2_6e_zotero_stage2_4j_src_209_chunk_001", "conditions": {"condition": "Cunninghamella elegans pre-grown pure culture incubation with 6:2 FTOH", "environment_matrix": "pure culture f'` |
| data/batches/stage2_6e_streaming_reviewed_records.jsonl | 1 | 1 | `27d623d6663b9627bfda018f72d10e953e111bda4804b94aaba8719006bfe529` | true | strict_jsonl_ok | `'{"chunk_id": "stage2_6e_zotero_stage2_4j_src_209_chunk_001", "conditions": {"condition": "Cunninghamella elegans pre-grown pure culture incubation with 6:2 FTOH", "environment_matrix": "pure culture f'` |
| data/batches/stage2_6e_streaming_validated_records.jsonl | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | true | strict_jsonl_ok | `''` |
| data/batches/stage2_6e_streaming_manual_review_records.jsonl | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | true | strict_jsonl_ok | `''` |
| data/batches/stage2_6e_streaming_rejected_records.jsonl | 3 | 3 | `895c4f4c26fa82baa62a8e9bd71ef4fcaaec0fcc0a8325e59fe0b98c13a06db2` | true | strict_jsonl_ok | `'{"chunk_id": "stage2_6e_zotero_stage2_4j_src_179_chunk_001", "database_write_ref": "data/batches/stage2_6e_streaming_rejected_records.jsonl", "doi": "10.1021/acs.est.4c13943", "evidence_tier": "none",'` |
| data/batches/stage2_6e_streaming_auxiliary_records.jsonl | 1 | 1 | `27d623d6663b9627bfda018f72d10e953e111bda4804b94aaba8719006bfe529` | true | strict_jsonl_ok | `'{"chunk_id": "stage2_6e_zotero_stage2_4j_src_209_chunk_001", "conditions": {"condition": "Cunninghamella elegans pre-grown pure culture incubation with 6:2 FTOH", "environment_matrix": "pure culture f'` |
| data/state/stage2_6e_streaming_source_status.jsonl | 27 | 27 | `f37c5f507967b0fcd5f1aa19836fb1a9729aae219bac9c7e6e7b089abda81486` | true | strict_jsonl_ok | `'{"artifact_refs": {"auxiliary_records_ref": "data/batches/stage2_6e_streaming_auxiliary_records.jsonl", "candidate_records_ref": "data/batches/stage2_6e_streaming_candidate_records.jsonl", "chunks_ref'` |
| data/state/stage2_6e_streaming_events.jsonl | 51 | 51 | `b559683f72717817b8cfad28b79b88a9b2beba232199a5446c578e4950338d41` | true | strict_jsonl_ok | `'{"agent": "TitleAbstractScreeningAgent", "batch_id": "stage2_6e_attachment_priority_stream", "event_id": "stage2_6e_attachment_priority_stream_zotero_stage2_4j_src_209_screening_00001", "event_type": '` |
