# Review PFAS Transformation Records

You are reviewing ECfinder transformation records against the source chunk.

Return JSON only.

## Accept Only If

- The evidence quote directly supports the parent/product/pathway relationship.
- The record is traceable to `source_id` and `chunk_id`.
- The context is natural environment or environmentally realistic.
- The product is named or clearly identified.

## Output Schema

```json
{
  "record_id": "string",
  "decision": "accepted|rejected|needs_reextract",
  "confidence": 0.0,
  "reasons": ["reason"],
  "corrected_record": {}
}
```
