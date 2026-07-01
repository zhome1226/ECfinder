# PFAS Transformation Extraction Skill

Extract only PFAS parent-to-product transformation candidates supported by selected chunk refs. Do not extract occurrence-only, monitoring-only, toxicity-only, food-web-only, analytical-method-only, review/background-only, or engineered-treatment-only content into the natural main database.

Return candidates with source_id, chunk_id, parent compound, product compound, condition, matrix, transformation type, evidence quote, and provenance. Every candidate must immediately enter ReviewAgent in the same closed-loop lineage.
