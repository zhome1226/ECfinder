# ExtractionAgent

## Purpose

Parse full text into auditable sections/chunks and extract PFAS transformation records.

## Inputs

- `data/interim/screened_sources.jsonl`
- `data/interim/download_status.jsonl`
- Local raw files under ignored `data/raw/`
- `configs/extraction_schema.yaml`
- `prompts/extract_transformation_records.md`

## Outputs

- `data/interim/parsed_sections.jsonl`
- `data/interim/chunks.jsonl`
- `data/extracted/pfas_transformation_records_raw.jsonl`

## Procedure

1. Parse PDF pages or HTML sections with source IDs and hashes.
2. Preserve section, page, table, figure, and caption context when available.
3. Weight chunks that mention PFAS, transformation processes, products, tables, or figures.
4. Extract only evidence-backed parent-to-product or pathway records.
5. Normalize common PFAS abbreviations without inventing external identifiers.

## Acceptance Criteria

- Every chunk has `source_id`, `chunk_id`, `section`, `text`, and `weight`.
- Every raw record validates against the extraction schema shape.
- Every raw record includes a short evidence quote from its chunk.
