# ECfinder

ECfinder is a stage-1 evidence pipeline for PFAS transformation pathways and transformation products reported under natural environmental conditions.

The repository is designed for traceable literature discovery, source screening, lawful full-text acquisition, PDF/HTML parsing, chunking, LLM-assisted extraction, rule/LLM review, and iterative re-extraction. It is not a model-training repository.

## Stage 1 Scope

- Search literature about PFAS transformation under natural environmental conditions.
- Screen titles and abstracts before acquiring full text.
- Store copyright PDFs only under `data/raw/pdfs/`; this path is ignored by Git.
- Parse available full text into local ignored section/chunk text, plus committed section/chunk indexes with hashes.
- Extract transformation pathway records with source-level provenance.
- Review each record against schema and evidence rules.

Every accepted transformation record must preserve `source_id`, `chunk_id`, page/section/table/figure/caption context, and a short evidence quote.

## Agents

- `SearchAgent`: literature discovery and metadata deduplication.
- `DownloadAgent`: title/abstract semantic screening and PDF/HTML acquisition.
- `ExtractionAgent`: sectioning, weighted chunking, and transformation record extraction.
- `ReviewAgent`: validation, rejection, and re-extraction routing.

## Copyright Boundary

Do not commit copyrighted PDFs, publisher HTML, or full parsed chunk text. Commit metadata, hashes, logs, chunk indexes, extraction outputs, review outputs, and reports only.

## Local Commands

```powershell
python -m ecfinder.cli inventory
python -m ecfinder.cli init-stage1-files
python -m ecfinder.cli search --limit 25
python -m ecfinder.cli review
```

Use the bundled Codex Python or a project virtual environment with dependencies installed from `pyproject.toml`.

## Production Autonomous Workflow

Stage 2.7 adds a Zotero-backed production daemon that continuously discovers runnable sources, streams each source from title/abstract screening through reviewed database write, checkpoints progress, and stops only when the library is exhausted or a configured safety stop is reached.

See `docs/PRODUCTION_AUTONOMOUS_WORKFLOW.md` for the workflow contract and `docs/OPERATION_MANUAL.md` for run, stop, resume, and validation commands.
