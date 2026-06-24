# Extract PFAS Transformation Records

You are extracting evidence-backed PFAS transformation records for ECfinder.

Return JSON only with `records` as a list. Do not infer beyond the supplied chunk. Do not extract treatment-only or model-only claims unless the chunk explicitly links them to natural environmental conditions.

## Required Evidence

Each record must include:

- `source_id`
- `chunk_id`
- parent PFAS or precursor name
- product name
- transformation process
- natural environmental context
- short evidence quote copied from the chunk
- evidence location: section, page/table/figure/caption when available

## Output Schema

```json
{
  "records": [
    {
      "source_id": "string",
      "chunk_id": "string",
      "parent_name": "string",
      "product_name": "string",
      "transformation_process": "biotransformation|biodegradation|phototransformation|hydrolysis|oxidation|reduction|natural_attenuation|unknown_environmental_transformation",
      "pathway_description": "string or null",
      "directionality": "parent_to_product|precursor_to_terminal_pfas|multi_step|ambiguous",
      "natural_environment_context": "string",
      "matrix": "string or null",
      "condition_type": "field_observation|environmental_microcosm|natural_attenuation_study|wastewater_or_leachate_environment|unclear",
      "evidence_quote": "string",
      "evidence_location": {
        "page": null,
        "section": "string",
        "table_id": null,
        "figure_id": null,
        "caption": null
      },
      "confidence": 0.0
    }
  ]
}
```
