# Job 7 lexical retrieval

V3 searches asset and scene search documents with PostgreSQL lexical functions and normalized token evidence. Filename matching is retained as a low-weight signal and cannot dominate scene narrative, structured, or visual evidence. Empty or unavailable OpenCLIP vectors safely degrade to lexical plus structured retrieval.

