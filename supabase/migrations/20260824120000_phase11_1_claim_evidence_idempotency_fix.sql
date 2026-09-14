begin;
delete from public.narrative_claim_evidence d
using public.narrative_claim_evidence keep
where d.claim_id=keep.claim_id
  and d.assertion_id is not distinct from keep.assertion_id
  and d.evidence_id is not distinct from keep.evidence_id
  and d.id>keep.id;
create unique index narrative_claim_evidence_null_safe_idx on public.narrative_claim_evidence(
 claim_id,
 coalesce(assertion_id,'00000000-0000-0000-0000-000000000000'::uuid),
 coalesce(evidence_id,'00000000-0000-0000-0000-000000000000'::uuid)
);
commit;
