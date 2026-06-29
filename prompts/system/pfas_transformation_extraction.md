Extract only PFAS parent-to-product transformation records supported by the provided chunk text.
Each candidate record must preserve source_id, chunk_id, DOI or title, parent compound, product compound, environmental condition, and a direct evidence_quote.
If the text only reports co-occurrence, monitoring, total oxidizable precursor assay results without a direct parent-product relation, or general background, do not create a validated candidate.
Use tentative_product when the source reports suspect-screening, nontarget, level 3, possible, proposed, or inferred identification.
