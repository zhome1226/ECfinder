# Agent Prompt and Schema Contracts

Prompt refs:
- `prompts/system/global_agent_policy.md`
- `prompts/system/natural_environment_boundary.md`
- `prompts/system/pfas_transformation_extraction.md`
- `prompts/system/evidence_grounded_review.md`
- `prompts/system/json_output_rules.md`

Schema refs:
- `schemas/source_metadata.schema.json`
- `schemas/screening_decision.schema.json`
- `schemas/chunk.schema.json`
- `schemas/transformation_record.schema.json`
- `schemas/review_decision.schema.json`
- `schemas/agent_task.schema.json`
- `schemas/batch_status.schema.json`

Agent tasks must pass refs rather than full source text. Extraction tasks reference metadata and chunk artifacts. Review tasks reference candidate record artifacts and evidence chunk artifacts.
