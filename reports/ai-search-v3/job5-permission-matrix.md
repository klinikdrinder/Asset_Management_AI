# Job 5 permission matrix

| Capability | Authority | Default / unknown | Role influence | Explicit approval |
|---|---|---|---|---|
| View | `asset_access_control.sensitivity_level`, `is_clinical`, `internal_usage_status`; `app_users.is_active/can_view_clinical` | General, non-clinical/unknown classification remains visible to active users; unknown sensitivity or explicit internal denial is denied | `can_view_clinical` permits sensitive/clinical view | Required for clinical capability |
| Preview / thumbnail | View function via asset RLS before media resolution | Same as view | Same as view | No separate implication |
| Download | View function + `app_users.can_download` + `asset_access_control.download_allowed` | NULL is denied | Global download capability is necessary but insufficient | Per-asset TRUE required |
| Edit metadata | Existing administrative/service workflows | No client write policy | Existing admin/service controls only | Required by workflow |
| Clinical access | `app_users.can_view_clinical` plus asset classification/sensitivity | No capability means deny sensitive/clinical content | Explicit user capability | Yes |
| Marketing use | `asset_access_control.marketing_usage_status` | UNKNOWN is not approved | No view/download implication | `APPROVED` required by future marketing workflow |
| External AI | `asset_access_control.external_ai_status` | NOT_REVIEWED/UNKNOWN is denied | Service-only function; user role does not imply eligibility | `ALLOWED` required |
| Administration | Existing `management_role` and server authorization | No implicit access | Existing admin/super-admin model | Existing authorization required |

Consent, classification, internal viewing, marketing, download, and external AI remain independent. No rule promotes one from another.
