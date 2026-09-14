# Job 5 central permission model

## Authoritative decisions

- View: `private.can_user_view_asset_for(user, asset)` and caller-bound `private/public.can_user_view_asset(asset)`.
- Download: `private.can_user_download_asset_for(user, asset)` and caller-bound wrapper.
- External processing: `private/public.can_asset_use_external_ai(asset)`, executable only by `service_role` through the public wrapper.
- Set-based retrieval: `private.authorized_asset_ids()` returns only the current authenticated app user's permitted asset IDs.

Privileged readers are SECURITY DEFINER only in the unexposed `private` schema, owned by `postgres`, fixed to `search_path=''`, and stripped of PUBLIC/anon execution. Public wrappers are SECURITY INVOKER and return booleans only. The server-only explicit-user download wrapper is executable solely by `service_role`.

## Decision rules

An asset is viewable only when the resolved `app_users` record is active, the asset is not failed/missing, an access-control row exists, internal use is not explicitly `NOT_ALLOWED`, sensitivity is known, and either the asset is general/internal non-clinical or the user has the existing `can_view_clinical` capability. No role automatically bypasses its explicit capability fields.

Download additionally requires `app_users.can_download=TRUE` and `asset_access_control.download_allowed=TRUE`. NULL is denied. External AI requires exactly `external_ai_status='ALLOWED'`; consent and marketing never imply it. Current UNKNOWN/NOT_REVIEWED values remain unchanged.

RLS on assets and all listed children calls the same view decision. Browser queries therefore cannot reveal restricted parent or derived records by guessed identifiers. Raw vectors and search projections retain no client table privileges.
