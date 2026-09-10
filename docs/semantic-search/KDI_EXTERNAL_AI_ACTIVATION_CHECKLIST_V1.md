# KDI External AI Activation Checklist V1

This checklist is documentation only. External AI remains disabled in the
accepted deterministic system (`EXTERNAL_AI_ENABLED=false`).

1. Confirm API account and billing are active.
2. Configure the API key in a secure server-side secret store.
3. Change the centralized `EXTERNAL_AI_ENABLED` flag explicitly.
4. Select and pin provider, model, and model version.
5. Configure spending limits and per-asset/batch budgets.
6. Verify bounded retry and rate-limit handling.
7. Verify token, cost, request ID, and latency logging.
8. Run the synthetic provider and disabled-gate tests.
9. Run one sanitized real API preflight and confirm network audit.
10. Confirm privacy, retention, and data-processing policy.
11. Approve one real 11th-asset activation test.
12. Verify fallback, rollback, and failure recovery before broader rollout.

No item above has been activated or executed by Phase 30.
