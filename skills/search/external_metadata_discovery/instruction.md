# External Metadata Discovery Skill

Discover external scholarly metadata through bounded, provider-specific adapters. This skill only returns metadata refs and provenance. It never downloads full text and never writes literature evidence directly to the database.

Required behavior:

- Run only configured query families with explicit result and candidate limits.
- Use structured metadata providers such as CrossRef, OpenAlex, Semantic Scholar, and PubMed when available.
- Gracefully skip unavailable providers or failed queries.
- Preserve provider, query_id, query_text, title, abstract, DOI, year, journal, authors, keywords, URL, open-access hints, and hashes.
- Deduplicate before adding external metadata to the production daemon.
- Keep output JSONL strict one-object-per-line.
