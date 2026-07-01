# Stage 2.4g User Zotero Steps

1. In Zotero, import `data/local_fulltext/zotero/stage2_4g_targets.ris` or `data/local_fulltext/zotero/stage2_4g_targets.bib`.
2. Create or use a collection named `ECfinder Stage 2.4g Fulltext Targets`.
3. Move the imported or already existing target items into that collection.
4. Select the collection items.
5. Right-click and run `Find Available PDF` / `Find Full Text`.
6. Wait until Zotero finishes all download attempts.
7. Confirm whether each item has a PDF or HTML attachment under the exact DOI item.
8. Return to this repository and run `python scripts/sync_zotero_stage2_4b_attachments.py`.

If Zotero cannot automatically download a PDF, use campus/library access to download the file lawfully, then drag it onto the matching Zotero item as an attachment.

Manual fallback: fill `data/local_fulltext/zotero/zotero_mapping_template.jsonl` with a local attachment path only after confirming the DOI/source_id mapping. The sync script will copy that file into the ignored local full-text cache and will not commit the original attachment.
