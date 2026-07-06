# Stage 2.8 Existing Agent Skill Inventory

existing_agents_found = 4
existing_skills_found = 14
agents_converted_or_merged = 2

| path | type | agent | skill_id | purpose | migration_action | notes |
| --- | --- | --- | --- | --- | --- | --- |
| agents/DownloadAgent.md | agent_md | DownloadAgent |  | download | merge_with_existing | Legacy DownloadAgent lawful access constraints merged into lawful and external fulltext resolution contracts. |
| agents/ExtractionAgent.md | agent_md | ExtractionAgent |  | extraction | keep | Existing tracked artifact. |
| agents/ReviewAgent.md | agent_md | ReviewAgent |  | review | keep | Existing tracked artifact. |
| agents/SearchAgent.md | agent_md | SearchAgent |  | search | merge_with_existing | Legacy SearchAgent strategy merged into search_planning and external metadata discovery contracts. |
| configs/extraction_schema.yaml | config |  |  | extraction | keep | Existing tracked artifact. |
| configs/review_rules.yaml | config |  |  | review | keep | Existing tracked artifact. |
| configs/search_queries.yaml | config |  |  | search | keep | Existing tracked artifact. |
| prompts/extract_transformation_records.md | prompt |  |  | extraction | manual_review | Existing tracked artifact. |
| prompts/reextract_from_failed_chunk.md | prompt |  |  | parse | manual_review | Existing tracked artifact. |
| prompts/review_transformation_records.md | prompt |  |  | review | manual_review | Existing tracked artifact. |
| prompts/screen_title_abstract.md | prompt |  |  | screening | manual_review | Existing tracked artifact. |
| prompts/system/evidence_grounded_review.md | prompt |  |  | review | manual_review | Existing tracked artifact. |
| prompts/system/global_agent_policy.md | prompt |  |  | other | manual_review | Existing tracked artifact. |
| prompts/system/json_output_rules.md | prompt |  |  | other | manual_review | Existing tracked artifact. |
| prompts/system/natural_environment_boundary.md | prompt |  |  | other | manual_review | Existing tracked artifact. |
| prompts/system/pfas_transformation_extraction.md | prompt |  |  | extraction | manual_review | Existing tracked artifact. |
| schemas/agent_task.schema.json | schema |  |  | other | keep | Existing tracked artifact. |
| schemas/batch_status.schema.json | schema |  |  | other | keep | Existing tracked artifact. |
| schemas/chunk.schema.json | schema |  |  | parse | keep | Existing tracked artifact. |
| schemas/review_decision.schema.json | schema |  |  | review | keep | Existing tracked artifact. |
| schemas/screening_decision.schema.json | schema |  |  | screening | keep | Existing tracked artifact. |
| schemas/source_metadata.schema.json | schema |  |  | metadata | keep | Existing tracked artifact. |
| schemas/transformation_record.schema.json | schema |  |  | other | keep | Existing tracked artifact. |
| scripts/audit_zotero_library_scope.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/check_zotero_control_capabilities.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/run_zotero_auto_fulltext_cycle.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/sync_available_zotero_attachments.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/sync_zotero_stage2_4b_attachments.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/validate_stage2_4i_zotero_auto_fulltext.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/zotero_create_missing_items.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/zotero_poll_attachments.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/zotero_stage2_4i_common.py | script |  |  | metadata | keep | Existing tracked artifact. |
| scripts/zotero_trigger_find_fulltext.py | script |  |  | metadata | keep | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/CHANGELOG.md | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/examples.jsonl | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/input.schema.json | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/instruction.md | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/output.schema.json | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/database_write/reviewed_record_database_write/skill.yaml | skill | DatabaseWriteAgent | reviewed_record_database_write_v1 | review | keep | Existing tracked artifact. |
| skills/download/external_fulltext_resolution/skill.yaml | skill | ExternalDownloadAgent | external_fulltext_resolution_v1 | download | keep | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/CHANGELOG.md | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/examples.jsonl | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/input.schema.json | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/instruction.md | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/output.schema.json | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/download/lawful_fulltext_resolution/skill.yaml | skill | DownloadAgent | lawful_fulltext_resolution_v1 | download | keep | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/CHANGELOG.md | unknown |  |  | extraction | manual_review | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/examples.jsonl | unknown |  |  | extraction | manual_review | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/input.schema.json | unknown |  |  | extraction | manual_review | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/instruction.md | unknown |  |  | extraction | manual_review | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/output.schema.json | unknown |  |  | extraction | manual_review | Existing tracked artifact. |
| skills/extraction/pfas_transformation_extraction/skill.yaml | skill | ExtractionAgent | pfas_transformation_extraction_v1 | extraction | keep | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/CHANGELOG.md | unknown |  |  | parse | manual_review | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/examples.jsonl | unknown |  |  | parse | manual_review | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/input.schema.json | unknown |  |  | parse | manual_review | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/instruction.md | unknown |  |  | parse | manual_review | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/output.schema.json | unknown |  |  | parse | manual_review | Existing tracked artifact. |
| skills/parse/chunk_relevance_filter/skill.yaml | skill | ChunkAgent | chunk_relevance_filter_v1 | parse | keep | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/CHANGELOG.md | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/examples.jsonl | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/input.schema.json | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/instruction.md | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/output.schema.json | unknown |  |  | download | manual_review | Existing tracked artifact. |
| skills/parse/fulltext_parse_chunk/skill.yaml | skill | ParseAgent | fulltext_parse_chunk_v1 | download | keep | Existing tracked artifact. |
| skills/review/evidence_grounded_review/CHANGELOG.md | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/review/evidence_grounded_review/examples.jsonl | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/review/evidence_grounded_review/input.schema.json | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/review/evidence_grounded_review/instruction.md | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/review/evidence_grounded_review/output.schema.json | unknown |  |  | review | manual_review | Existing tracked artifact. |
| skills/review/evidence_grounded_review/skill.yaml | skill | ReviewAgent | evidence_grounded_review_v1 | review | keep | Existing tracked artifact. |
| skills/screening/title_abstract_screening/CHANGELOG.md | unknown |  |  | screening | manual_review | Existing tracked artifact. |
| skills/screening/title_abstract_screening/examples.jsonl | unknown |  |  | screening | manual_review | Existing tracked artifact. |
| skills/screening/title_abstract_screening/input.schema.json | unknown |  |  | screening | manual_review | Existing tracked artifact. |
| skills/screening/title_abstract_screening/instruction.md | unknown |  |  | screening | manual_review | Existing tracked artifact. |
| skills/screening/title_abstract_screening/output.schema.json | unknown |  |  | screening | manual_review | Existing tracked artifact. |
| skills/screening/title_abstract_screening/skill.yaml | skill | TitleAbstractScreeningAgent | title_abstract_screening_v1 | screening | keep | Existing tracked artifact. |
| skills/search/external_metadata_discovery/skill.yaml | skill | ExternalSearchAgent | external_metadata_discovery_v1 | search | keep | Existing tracked artifact. |
| skills/search/metadata_search/CHANGELOG.md | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/metadata_search/examples.jsonl | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/metadata_search/input.schema.json | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/metadata_search/instruction.md | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/metadata_search/output.schema.json | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/metadata_search/skill.yaml | skill | MetadataAgent | metadata_search_v1 | search | keep | Existing tracked artifact. |
| skills/search/search_planning/CHANGELOG.md | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/search_planning/examples.jsonl | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/search_planning/input.schema.json | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/search_planning/instruction.md | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/search_planning/output.schema.json | unknown |  |  | search | manual_review | Existing tracked artifact. |
| skills/search/search_planning/skill.yaml | skill | SearchAgent | search_planning_v1 | search | keep | Existing tracked artifact. |
| skills/skill_manager/CHANGELOG.md | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/skill_manager/examples.jsonl | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/skill_manager/input.schema.json | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/skill_manager/instruction.md | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/skill_manager/output.schema.json | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/skill_manager/skill.yaml | skill | SkillManagerAgent | skill_manager_agent_v1 | other | keep | Existing tracked artifact. |
| skills/skill_registry.json | unknown |  |  | other | manual_review | Existing tracked artifact. |
| skills/supervisor/CHANGELOG.md | unknown |  |  | supervisor | manual_review | Existing tracked artifact. |
| skills/supervisor/examples.jsonl | unknown |  |  | supervisor | manual_review | Existing tracked artifact. |
| skills/supervisor/input.schema.json | unknown |  |  | supervisor | manual_review | Existing tracked artifact. |
| skills/supervisor/instruction.md | unknown |  |  | supervisor | manual_review | Existing tracked artifact. |
| skills/supervisor/output.schema.json | unknown |  |  | supervisor | manual_review | Existing tracked artifact. |
| skills/supervisor/skill.yaml | skill | SupervisorAgent | supervisor_agent_v1 | supervisor | keep | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/CHANGELOG.md | unknown |  |  | metadata | manual_review | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/examples.jsonl | unknown |  |  | metadata | manual_review | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/input.schema.json | unknown |  |  | metadata | manual_review | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/instruction.md | unknown |  |  | metadata | manual_review | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/output.schema.json | unknown |  |  | metadata | manual_review | Existing tracked artifact. |
| skills/zotero/zotero_attachment_sync/skill.yaml | skill | ZoteroAgent | zotero_attachment_sync_v1 | metadata | keep | Existing tracked artifact. |
