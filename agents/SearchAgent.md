# SearchAgent

## Purpose

Find candidate literature on PFAS transformation pathways and transformation products under natural environmental conditions.

## Inputs

- `configs/search_queries.yaml`
- Optional prior metadata in `data/interim/search_results.jsonl`

## Outputs

- `data/interim/search_results.jsonl`
- `reports/search_strategy.md`
- `reports/query_performance.md`
- Agent run log under `logs/agent_runs/`

## Procedure

1. Load query concepts and Boolean strings.
2. Search structured sources first: CrossRef, PubMed, and OpenAlex fallback.
3. Deduplicate by normalized DOI; if DOI is absent, use normalized title plus first author.
4. Assign `source_id` from DOI or title hash.
5. Record source, query_id, timestamp, hit rank, title, abstract, DOI, year, journal, URL, and raw provider.
6. Do not download PDFs.

## Acceptance Criteria

- Every result has `source_id`, `query_id`, `title`, and `retrieved_at`.
- Every failed source/query pair has a log entry.
- Search output is append-only JSONL and can be rerun.
