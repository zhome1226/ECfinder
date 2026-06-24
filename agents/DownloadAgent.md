# DownloadAgent

## Purpose

Screen candidate papers by title/abstract and acquire lawful full text without committing copyrighted content.

## Inputs

- `data/interim/search_results.jsonl`
- `prompts/screen_title_abstract.md`

## Outputs

- `data/interim/screened_sources.jsonl`
- `data/interim/download_status.jsonl`
- Local ignored files under `data/raw/pdfs/` or `data/raw/html/`

## Procedure

1. Apply deterministic prefilters for PFAS and transformation terms.
2. Use the title/abstract LLM prompt where an LLM runtime is available.
3. Prefer open access PDF or PMC/full-text HTML.
4. Store raw PDF/HTML locally only; record SHA-256, byte size, URL, access timestamp, and license/access notes.
5. If full text is not available, keep metadata and mark `download_status=unavailable_or_paywalled`.

## Acceptance Criteria

- No raw PDF or publisher HTML is tracked by Git.
- Every screened source has a decision, reason, and confidence.
- Every local raw file has a hash in `download_status.jsonl`.
