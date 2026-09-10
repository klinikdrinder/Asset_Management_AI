# KDI Phase 17 — Broad Hybrid Candidate Retrieval

Phase 17 introduces an internal `CandidateSet` retriever. It unions canonical concepts, approved expanded concepts, READY full-text documents, accepted OCR/transcript literals, deterministic metadata, multilingual E5 text vectors, and OpenCLIP text-to-visual vectors. The live RPC requires exact representation/provider/model/checkpoint/dimension compatibility before cosine comparison.

Candidates are rolled up to asset IDs with child evidence provenance. The requested result count only scales a broad retrieval target; it never caps retrieval. No final ranking, authorization filtering, asset exposure, or result-count enforcement occurs in this phase.

The current semantic evaluation scope is the frozen 10-asset canonical pilot index. The locked 90/30/30 DEV, validation, and blind candidate-retrieval splits pass at 100% Candidate Recall@10; DEV was repeated from clean processes. Four unrelated-domain regressions and every locked no-match case return an empty candidate set.
