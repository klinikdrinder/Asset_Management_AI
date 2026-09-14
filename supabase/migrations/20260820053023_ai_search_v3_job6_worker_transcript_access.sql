-- KDI AI Search V3 Job 6: allow only the trusted worker role to manage
-- transcript chunks. Public/anon/authenticated remain explicitly denied.
revoke all on table public.asset_transcript_chunks from public, anon, authenticated;
grant select, insert, update, delete on table public.asset_transcript_chunks to service_role;

do $$
declare
  v_sequence regclass;
begin
  v_sequence := pg_get_serial_sequence('public.asset_transcript_chunks', 'id')::regclass;
  if v_sequence is not null then
    execute format('revoke all on sequence %s from public, anon, authenticated', v_sequence);
    execute format('grant usage, select on sequence %s to service_role', v_sequence);
  end if;
end
$$;
