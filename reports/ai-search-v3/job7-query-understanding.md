# Job 7 query understanding

The deterministic parser extracts requested count, media/extension exclusions, treatment, anatomy, action, participant role, content/scene type, environment, shot type, and composition. Controlled codes are resolved from supported terms; unmatched text remains available to lexical and OpenCLIP retrieval. Default count is 5 and the bounded maximum is 50.

Follow-ups preserve the resolved prior query. `next` requests exclude already returned UUIDs; refinements such as `only videos` merge filters without requiring an LLM.

