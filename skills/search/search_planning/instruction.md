# Search Planning Skill

Plan controlled literature search queries by query family and source scope. Do not execute uncontrolled expansion in architecture-audit mode. Output queue refs and query refs only.

## Stage 2.8 Legacy SearchAgent Integration

Legacy `agents/SearchAgent.md` guidance is now part of this planning contract:

- Prefer structured scholarly metadata sources before broad web expansion.
- Search CrossRef, OpenAlex, PubMed, and Semantic Scholar through adapters.
- Deduplicate by normalized DOI first; if DOI is absent, use normalized title plus first author or title hash.
- Record query_id, provider, retrieval timestamp, hit rank, title, abstract, DOI, year, journal, URL, and source provenance.
- Do not download PDFs or HTML during search planning.
- Keep query execution bounded by explicit query-family and result-count limits.
