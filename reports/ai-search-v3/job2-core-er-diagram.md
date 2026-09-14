# Job 2 Core ER Diagram

```mermaid
erDiagram
  ASSETS ||--o{ ASSET_PEOPLE : observed_in
  PEOPLE o|--o{ ASSET_PEOPLE : verified_identity
  ASSETS ||--o{ ASSET_DERIVATIVES : generates
  ASSETS ||--|| ASSET_ACCESS_CONTROL : governed_by
  ASSETS ||--o{ AI_ANALYSIS_RUNS : analyzed_by
  AI_ANALYSIS_RUNS o|--o{ ASSET_DERIVATIVES : produced_by

  TREATMENTS o|--o{ TREATMENTS : parent_of
  TREATMENTS ||--o{ TREATMENT_ALIASES : has
  ANATOMY_TERMS o|--o{ ANATOMY_TERMS : parent_of
  LOCATIONS o|--o{ LOCATIONS : parent_of

  TREATMENTS o|--o{ ASSET_AI_PROFILES : primary_treatment
  ANATOMY_TERMS o|--o{ ASSET_AI_PROFILES : primary_anatomy
  LOCATIONS o|--o{ ASSET_AI_PROFILES : primary_location
```

`asset_people.person_id` is nullable: known verified people may link to `people`; anonymous patients remain unlinked while retaining non-identity observations.

Controlled parents use RESTRICT. Canonical references use SET NULL. Asset-owned operational metadata uses CASCADE only when its canonical asset is deliberately deleted.

