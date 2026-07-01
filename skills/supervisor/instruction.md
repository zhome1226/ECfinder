# Supervisor Agent Skill

Read source_status_board, task_registry, artifact_index, and skill_registry. Select the next runnable task and call the matching skill using task_id, skill_id, input_refs, schema_refs, and short_context only. Do not pass full project background, full abstracts, full chunks, or raw full text. Continue until no runnable tasks remain; blocked_external and manual_required do not stop other sources.
