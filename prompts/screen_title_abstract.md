# Screen Title And Abstract

You are screening literature for ECfinder stage 1.

Return JSON only.

## Include

Include a paper only if the title/abstract/metadata suggests all of the following:

- PFAS, a PFAS precursor, or a PFAS transformation product is discussed.
- Transformation, degradation, biotransformation, phototransformation, oxidation, precursor conversion, or transformation products are discussed.
- The setting is natural environment, environmental matrix, field observation, natural attenuation, wastewater/landfill context, or environmentally realistic microcosm.

## Exclude

Exclude papers that are only analytical methods, only exposure/toxicity, only engineered treatment with no environmental relevance, or only model prediction without literature evidence.

## Output Schema

```json
{
  "source_id": "string",
  "decision": "include|exclude|maybe",
  "confidence": 0.0,
  "reason": "short reason",
  "matched_terms": ["term"]
}
```
