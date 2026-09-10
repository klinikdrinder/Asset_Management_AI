-- Job 2 advisor completion: cover the nullable reviewer foreign key.
create index asset_access_control_reviewed_by_idx
  on public.asset_access_control(reviewed_by)
  where reviewed_by is not null;
