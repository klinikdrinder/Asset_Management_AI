# Job 4 conversational query model

Each turn is preserved as raw input plus a fully resolved interpretation. Child turns point to their parent; prior rows are never overwritten.

## Examples

1. `Find male patients discussing frontal hairline design.`
   - `query_type=NEW_SEARCH`, `requested_count=5`, `count_explicit=false`, `result_offset=0`, `media_type=video`
   - parsed/structured/semantic JSON records patient gender, frontal hairline, discussion intent.

2. `Give me 12.`
   - parent is turn 1; `query_type=COUNT_CHANGE`, `requested_count=12`, `count_explicit=true`
   - resolved intent retains the prior semantic and structured filters.

3. `Only Dr Inder.`
   - parent is turn 2; `query_type=FILTER_CHANGE`
   - resolved query retains male patient/hairline design and adds verified person code `DR_INDER_001`.

4. `Give me another 10.`
   - parent is turn 3; `query_type=NEXT_RESULTS`, `requested_count=10`, `count_explicit=true`
   - `result_offset` equals the prior returned count; resolved semantic intent is unchanged.

The requested count is a target, not a relevance guarantee. Retrieval may return fewer results rather than pad weak matches. Unique `(search_query_id, asset_id)` prevents duplicate top-level assets; the best scene/keyframe/transcript and timestamps stay attached to that ranked asset.
