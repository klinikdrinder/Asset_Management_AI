# Job 7 benchmark results

Twenty controlled queries covered visual, structured, combined, and negative cases. Median timings were 55.49 ms for query embedding, 349.11 ms for database retrieval/ranking, and 402.64 ms end-to-end.

Grounded examples included `frontal scalp` (3 results), `FUE implantation recipient scalp` (1), `facial injection close-up` (2), `neck injection` (1), and `clinician using device on scalp` (supported top result). Unsupported exact intents such as `clinician pointing at hairline` returned zero rather than padded guesses. `outdoor walking`, `car driving on highway`, and `dental surgery` returned zero after applying the documented domain-aware visual-only threshold.

Manual ground truth was recorded only where Job 6 evidence supports it; no labels or transcript evidence were fabricated.
