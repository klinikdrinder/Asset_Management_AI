# Job 7 performance

- Queries: 20
- OpenCLIP embedding median: 55.49 ms
- PostgreSQL retrieval plus ranking median: 349.11 ms
- End-to-end median: 402.64 ms
- Cold post-deployment embedding request: 6,712 ms

The SQL aggregates signals in one permission-scoped function, avoiding per-result N+1 database retrieval. HNSW indexes support all current 512-dimensional visual-vector tables.
