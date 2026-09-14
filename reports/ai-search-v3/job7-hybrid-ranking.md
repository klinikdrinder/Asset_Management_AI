# Job 7 hybrid ranking

Documented normalized weights:

- structured intent: 0.30
- scene visual: 0.20
- asset visual: 0.18
- asset lexical: 0.12
- scene lexical: 0.08
- keyframe visual: 0.07
- filename: 0.05

All inputs are clamped/normalized before aggregation. Hard structured filters gate mismatches. Results below the 0.08 relevance threshold are omitted; unsupported visual-only, non-KDI-domain queries require 0.18. This keeps domain visual discovery available while preventing unrelated padding. One asset is returned once with aggregated evidence and matched scene timestamps.
