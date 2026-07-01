# Stage 2.6 Token Optimization Plan

1. SupervisorAgent never sends full project context.
2. Screening uses title/abstract only.
3. Parsing is deterministic and non-LLM.
4. Chunk relevance precedes extraction.
5. Review receives candidate plus evidence snippet only.
6. DOI, title/abstract, chunk, and candidate hashes drive cache reuse.
