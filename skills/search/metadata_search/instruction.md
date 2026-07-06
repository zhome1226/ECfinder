# Metadata Search Skill

Resolve DOI/title metadata once, using DOI as the primary key and normalized title as fallback. Return metadata refs and hashes only. Do not retrieve full text and do not pass long abstracts to downstream agents except through a metadata artifact ref.

## Stage 2.8 External Metadata Integration

External metadata records may arrive from CrossRef, OpenAlex, Semantic Scholar, PubMed, or another lawful metadata provider. The skill keeps these records as metadata-only artifacts until title/abstract screening decides whether a source can proceed to fulltext resolution.

Required metadata behavior:

- Preserve `source_origin`, `source_provider`, `query_id`, `query_text`, `metadata_hash`, `title_abstract_hash`, and `dedup_key`.
- Use DOI deduplication first; otherwise use a normalized title hash.
- Never treat a search result as evidence or a database record.
- Never retrieve or embed full text as part of metadata search.
