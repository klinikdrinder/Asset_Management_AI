begin;
-- These three Step 14 synchronization fixtures are 43-47 byte placeholder
-- payloads labelled image/png. Pillow cannot decode them and Drive provides no
-- thumbnail. They are not supported visual media and must not receive invented
-- embeddings or remain mysterious failures.
update public.asset_visual_index_jobs j set
  status='NOT_APPLICABLE', failure_code='CORRUPT_IMAGE',
  failure_detail='Step 14 synchronization fixture is not a decodable image and has no Drive thumbnail',
  completed_at=now(), updated_at=now(), claim_owner=null, claimed_at=null, claim_expires_at=null
from public.assets a where a.id=j.asset_id and j.status='FAILED'
  and a.file_name in ('step14-retry.png','step14-unique.png')
  and a.mime_type='image/png' and a.size_bytes between 1 and 100;
commit;
