# Stage 2.6 Supervisor Agent Design

SupervisorAgent reads source_status_board, task_registry, artifact_index, and skill_registry. It sends task_id, skill_id, input_refs, schema_refs, and short_context only, then continues until no runnable tasks remain.
