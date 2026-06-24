# Re-Extract From Failed Chunk

The previous extraction from this chunk failed review. Re-extract only records that are directly supported by the chunk.

Focus on:

- named parent and product pairs
- explicit precursor-to-product relationships
- table rows or figure captions that contain product names
- natural environmental matrix or environmentally realistic microcosm context

Return JSON only using the extraction schema. If no valid record exists, return:

```json
{"records": []}
```
