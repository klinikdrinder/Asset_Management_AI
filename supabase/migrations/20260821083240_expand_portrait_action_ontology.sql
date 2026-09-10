insert into public.actions(code,name,category,description,is_active,metadata)
values
('LOOKING_AT_CAMERA','Looking at Camera','BEHAVIOUR','Subject is visibly looking toward the camera.',true,'{}'::jsonb),
('POSING_FOR_CAMERA','Posing for Camera','BEHAVIOUR','Subject is intentionally posed for a still or portrait image.',true,'{}'::jsonb)
on conflict (code) do update set name=excluded.name,category=excluded.category,description=excluded.description,is_active=true,updated_at=now();;
