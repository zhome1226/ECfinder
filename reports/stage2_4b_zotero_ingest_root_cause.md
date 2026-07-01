# Stage 2.4b Zotero Attachment Ingest Root Cause

diagnosis_status = completed
target_manifest_sources = 12
zotero_exact_doi_items_found = 5
zotero_exact_doi_items_missing = 7
zotero_exact_doi_items_without_attachment = 5
zotero_target_attachments_existing = 0
attachments_synced_to_local_fulltext = 0
local_fulltext_files_found = 0
parsed_stage2_4b_sources = 0
validated_stage2_4b_records = 0

root_cause = Stage 2.4b ingest was not seeing full text because the target Zotero items currently have no attached PDF/HTML files, and the remaining targets have no exact-DOI Zotero item. The ingest script also previously had no Zotero attachment discovery layer, so a future attached target file would not be synchronized automatically into the ignored local_fulltext cache.

why_records_only_from_one_source = The existing validated records come from stage2_4_src_001 / 10.1021/acs.estlett.8b00148, which has a local cached HTML artifact and 23 parsed chunks. The Stage 2.4b high-priority targets remain metadata-only because no exact target PDF/HTML is present in data/local_fulltext/stage2_4b and no exact-DOI Zotero attachment was found.

fix_added = scripts/sync_zotero_stage2_4b_attachments.py now performs read-only Zotero SQLite discovery, accepts exact DOI matches only, copies supported target attachments into ignored local_fulltext paths when present, updates fulltext_manifest.jsonl, and writes data/batches/stage2_4b_zotero_attachment_status.jsonl plus reports/stage2_4b_zotero_attachment_diagnosis.md.

boundary_note = Similar Zotero PDFs were found for related PFAS papers, but they have different DOI values and were not used as substitutes for the Stage 2.4b targets.
