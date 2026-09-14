# Job 5 search permission integration

Future Hybrid Search V3 must begin from `private.authorized_asset_ids()` (or an equivalent join using the same central predicate), then join permitted assets to asset/scene search documents and compatible embeddings, score only that permitted set, and finally rank/top-N. Restricted candidates must never enter score distributions, counts, offsets, or result logs.

Recommended logical path:

```sql
with permitted as materialized (
  select asset_id from private.authorized_asset_ids()
), candidates as (
  select d.* from public.asset_search_documents d
  join permitted p using (asset_id)
  where d.build_status='READY'
)
-- retrieve/score/rank candidates here
```

The helper is STABLE and set-based, joining one current `app_users` row to indexed access-control/assets rows. Permission indexes cover view eligibility, explicit download, and explicit external AI. At larger scale, EXPLAIN with production-shaped selectivity should determine whether the CTE should be materialized per request. Never call a procedural permission function thousands of times when the permitted relation can be joined once.

V1/V2 remain unchanged and are not the V3 integration path.
