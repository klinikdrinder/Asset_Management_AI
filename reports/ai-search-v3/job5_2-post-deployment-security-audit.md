# Job 5.2 post-deployment security audit

- RLS is enabled on all 15 explicitly checked sensitive Job 3/4/5 tables.
- Effective TRUNCATE is false for both `anon` and `authenticated` across every public base table.
- Central view, download, and external-AI functions passed the transactional matrix and rolled back.
- Security-definer functions retain fixed search paths. No database function or ACL changed in Job 5.2, and no unsafe PUBLIC execute was introduced.
- Raw embedding and search-document access remains backend controlled; Job 5 RLS/security behavior is unchanged.
- Search-history ownership isolation remains unchanged and covered by the 240-test dashboard suite and Job 5 verification.
- V1/V2 hashes remain `6b179fcb951bf228d434b44baad56c38` and `14f4f1347d13fa2201ac6e20e7e5020b`.

Supabase advisors report pre-existing informational no-policy tables, public-schema extension warnings, intentional authenticated V1/V2 security-definer RPC warnings, legacy missing-FK indexes, unused indexes on empty V3 tables, and known duplicate legacy indexes. Job 5.2 introduced none of them and changed no schema.

## Resume verification (2026-08-20)

- TypeScript typecheck: PASS.
- Dashboard/auth/media/search/security suite: PASS, 240/240.
- Focused Job 5 central download suite: PASS, 2/2.
- Python suite: PASS, 646 tests plus 74 subtests.
- The first unscoped Python collection attempt failed because a duplicate utility/test basename and relocation-stale virtual-environment metadata confused collection. The authoritative `tests` run with `PYTHONPATH=D:\Asset_Management_AI\src;D:\Asset_Management_AI` passed fully.
- Live unauthenticated and direct-route download denials: PASS; denial leakage: PASS.
- Exact REST counts reconfirmed the preservation baseline and all 881 access-control rows remain `NOT_REVIEWED`.
- Raw `asset_ai_profiles` and `asset_transcript_chunks` remain intentionally unavailable through the REST role used for this recheck (HTTP 403), consistent with backend-only protection; their preserved 10/0 counts remain supported by the prior database-level Job 5.2 verification and unchanged schema/data state.
- No schema, RLS policy, function, grant, asset status, media, embedding, or Job 3/4 intelligence row was changed during the resume.
