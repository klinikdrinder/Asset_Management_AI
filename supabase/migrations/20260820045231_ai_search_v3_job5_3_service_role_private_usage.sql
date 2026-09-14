-- Job 5.3: public service-only permission wrappers are SECURITY INVOKER and
-- call their narrowly granted private implementations. EXECUTE was already
-- granted to service_role, but schema USAGE was missing, causing the wrapper
-- to fail before reaching the permission function.
grant usage on schema private to service_role;
