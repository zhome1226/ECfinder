# Failure Analysis

Rejected or re-extraction records: 13

Reviewer status counts: `{"needs_reextract": 13}`

Reason counts: `{"confidence_below_accept_threshold": 13}`

Current pilot uses a conservative regex fallback extractor. All non-empty raw candidates should be treated as re-extraction tasks unless a later LLM or manual review confirms the parent-product relationship against the source chunk.
