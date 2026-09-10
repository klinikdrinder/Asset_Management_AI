# Job 2 Controlled Ontology Seed

The seed is deterministic and idempotent through stable codes and `ON CONFLICT` upserts. No patient or other person identity was seeded, and no AI-generated phrase was promoted automatically.

## Treatments — 12

Hierarchy:

- HAIR_RESTORATION
  - HAIR_TRANSPLANT
    - HAIR_TRANSPLANT_FUE
      - FUE_CONSULTATION
      - FUE_HAIRLINE_DESIGN
      - FUE_DONOR_ASSESSMENT
      - FUE_ANAESTHESIA
      - FUE_EXTRACTION
      - FUE_GRAFT_PREPARATION
      - FUE_IMPLANTATION
      - FUE_POST_OP
      - FUE_FOLLOW_UP

## Treatment aliases — 6

Four aliases map to `FUE_HAIRLINE_DESIGN`: hairline planning, hairline drawing, frontal hairline planning, frontal design.

Two map to `HAIR_TRANSPLANT_FUE`: follicular unit extraction and FUE transplant. Normalization is lower-case, trimmed, and whitespace-collapsed; uniqueness is language-aware.

## Anatomy — 25

Three roots: SCALP, FACE, NECK. SCALP has the seven requested hair/scalp regions. FACE contains UPPER_FACE, PERIOCULAR, MIDFACE, and LOWER_FACE with all requested children. These are anatomical locations only, never diagnoses.

## Actions — 22

Seeded communication, gesture, clinical, behavior, movement, position, and FUE-procedure verbs: consulting, discussing, talking, listening, explaining, pointing, examining, marking, drawing hairline, cleansing, injecting, holding syringe, using device, checking symmetry, touching, looking in mirror, smiling, walking, lying down, extracting grafts, sorting grafts, and implanting grafts.

## Locations — 11

Generic roots: CLINIC, OUTDOOR, HOME, HOTEL. Under CLINIC: consultation room, treatment room, operating room, reception, waiting area, corridor, and office. No unverified KDI-specific room identity was invented.

## Verification

Duplicate code groups and duplicate normalized-alias/language groups are all zero. Re-running the seed updates controlled labels/relationships without adding duplicate rows.

