"""KDI extraction contract v2 - ontology-selective visual inference.

A NEW, versioned contract added *alongside* the locked
``ClaudeSemanticProvider.LAYER_CONTRACT`` in ``claude_provider.py``; that file is
left intact.  Nothing imports this module in a run yet - it is presented for
review before anything uses it.

What changes from v1
--------------------
* v1 forbids naming any clinical procedure unless the term appears in supplied
  text, forcing TREATMENT_PROCEDURE to UNKNOWN on every purely-visual asset.
  v2 permits visual inference of treatment, anatomy, action, environment, role
  and relationship - but only by *selecting from an enumerated vocabulary*
  injected into the prompt, never by free wording.
* Each selected concept carries its own confidence and, when OBSERVED, at least
  one frame/keyframe evidence reference.
* ``UNDETERMINED`` is always selectable and MUST be used instead of guessing a
  specific code when the evidence is insufficient.
* A **named-procedure confidence floor** (0.7): a specific TREATMENT_PROCEDURE
  code is a clinical assertion on a patient record, so below 0.7 it degrades to
  ``UNDETERMINED`` rather than guessing which procedure.  Generic concepts keep
  the ordinary low-confidence threshold (0.4).
* The **raw model output is always preserved** next to the resolved code - even
  when a concept degrades to UNDETERMINED or fails resolution - so the operator
  can see what the model was trying to say, not only what survived.

What stays identical to v1
--------------------------
* The 18 layer ids, in the same order.
* The layer-level state vocabulary: OBSERVED | FALSE | UNKNOWN | NOT_APPLICABLE.
* One JSON object, strictly validated, no prose.

Controlled-vocabulary layers (7) and their resolver domains:

  PEOPLE_ROLES                 -> person_roles (enum)
  ANATOMY                      -> anatomy_terms
  TREATMENT_PROCEDURE          -> treatments
  ACTIONS_EVENTS               -> actions
  RELATIONSHIPS                -> relationship_types (enum)
  CLINICAL_VISUAL_OBSERVATIONS -> clinical_observation_definitions
  ENVIRONMENT                  -> locations

The remaining 11 layers have no controlled vocabulary; there v2 keeps v1
behaviour: a short grounded ``code`` phrase (open vocabulary) that the resolver
records as ``no_ontology_domain``.

Persistence contract (for the Part C writer; see the companion migration
``..._ai_search_v3_concept_provenance.sql``): every row written to
``asset_search_concepts_v2`` also stores, per row and queryable:
  - ``raw_concept``      : the exact code/text the model emitted
  - ``model_confidence`` : the per-concept confidence the model reported
  - ``resolution_method``: exact | alias | normalized | undetermined |
                           degraded_named_procedure | unresolved |
                           no_ontology_domain
``finalize_concept`` below produces exactly those fields deterministically, so
enforcement never depends on the model obeying the prose alone.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .ontology_resolver import DOMAIN_BY_TYPE, OntologyResolver

CONTRACT_VERSION = "kdi-extraction-contract-v2"

LAYER_IDS = (
    "ASSET_IDENTITY_PROVENANCE", "GLOBAL_ASSET_UNDERSTANDING",
    "TEMPORAL_SCENE_STRUCTURE", "PEOPLE_ROLES", "PERSON_APPEARANCE",
    "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS", "RELATIONSHIPS",
    "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT", "CINEMATOGRAPHY",
    "COMPOSITION", "SPEECH_TRANSCRIPT_AUDIO", "OCR_VISIBLE_TEXT",
    "MARKETING_CONTENT_USAGE", "SEMANTIC_NARRATIVE", "SEARCH_EMBEDDINGS",
)
STATES = ("OBSERVED", "FALSE", "UNKNOWN", "NOT_APPLICABLE")

# layer_id -> concept_type stored on asset_search_concepts_v2 (mirrors the
# CASE mapping in dashboard/scripts/phase11-1-import.ts).
LAYER_TO_CONCEPT_TYPE: dict[str, str] = {
    "PEOPLE_ROLES": "ROLE", "ANATOMY": "ANATOMY", "TREATMENT_PROCEDURE": "TREATMENT",
    "ACTIONS_EVENTS": "ACTION", "RELATIONSHIPS": "RELATIONSHIP",
    "CLINICAL_VISUAL_OBSERVATIONS": "CLINICAL_OBSERVATION", "ENVIRONMENT": "ENVIRONMENT",
    "MARKETING_CONTENT_USAGE": "CONTENT_TYPE", "OCR_VISIBLE_TEXT": "OCR",
    "SPEECH_TRANSCRIPT_AUDIO": "SPOKEN_CONCEPT",
}

# The 7 controlled layers, in prompt-display order.
CONTROLLED_LAYERS: tuple[str, ...] = (
    "PEOPLE_ROLES", "ANATOMY", "TREATMENT_PROCEDURE", "ACTIONS_EVENTS",
    "RELATIONSHIPS", "CLINICAL_VISUAL_OBSERVATIONS", "ENVIRONMENT",
)

UNDETERMINED = "UNDETERMINED"
# Concepts at or below this confidence are stored but flagged, never dropped.
LOW_CONFIDENCE_THRESHOLD = 0.4
# A specific named TREATMENT_PROCEDURE code needs at least this confidence;
# below it the concept degrades to UNDETERMINED (kept, flagged).
NAMED_PROCEDURE_LAYER = "TREATMENT_PROCEDURE"
NAMED_PROCEDURE_CONFIDENCE_FLOOR = 0.7

# Technique-level treatment codes assert a specific surgical *technique*, which
# can only be read from donor-site appearance. They are permitted only when
# donor evidence (DONOR_REGION_VISIBLE / EXTRACTION_SITES_VISIBLE) is also
# asserted on the same asset; otherwise they demote to the generic
# HAIR_TRANSPLANT (which the recipient-area evidence still supports) - NOT to
# UNDETERMINED. This is a separate instrument from the 0.7 confidence floor: a
# recipient-only photo can yield a high-confidence FUE the evidence can't back.
TECHNIQUE_LEVEL_TREATMENTS = {"HAIR_TRANSPLANT_FUE", "FUE_IMPLANTATION", "FUE_DONOR_ASSESSMENT"}
TECHNIQUE_TREATMENT_PREFIXES = ("FUT",)  # future FUT-* technique codes
DONOR_EVIDENCE_CODES = {"DONOR_REGION_VISIBLE", "EXTRACTION_SITES_VISIBLE"}
GENERIC_TREATMENT_FALLBACK = "HAIR_TRANSPLANT"


def _is_technique_treatment(code: str) -> bool:
    return code in TECHNIQUE_LEVEL_TREATMENTS or any(
        str(code).startswith(p) for p in TECHNIQUE_TREATMENT_PREFIXES)


def _concept_type(layer_id: str) -> str:
    return LAYER_TO_CONCEPT_TYPE.get(layer_id, "SEMANTIC_CONCEPT")


CONTRACT_HEADER = (
    "You are indexing a hair-transplant / aesthetic-medicine media asset for "
    "search. Return ONE JSON object and nothing else - no prose, no markdown "
    "fence.\n\n"
    "Schema:\n"
    "{\n"
    '  "narrative": "<two sentences describing only what the images show>",\n'
    '  "layers": [\n'
    "    {\n"
    '      "layer_id": "<one of the 18 ids below>",\n'
    '      "state": "OBSERVED|FALSE|UNKNOWN|NOT_APPLICABLE",\n'
    '      "evaluated": true,\n'
    '      "concepts": [\n'
    '        { "code": "<see selection rules>",\n'
    '          "confidence": <number 0.0-1.0>,\n'
    '          "evidence": ["frame:<index>"] }\n'
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Rules that stay fixed:\n"
    "- The layers array must contain EXACTLY these 18 layer_id values, each once:\n"
    "  {layers}\n"
    "- evaluated must always be true: it records that you examined the evidence.\n"
    "- state: OBSERVED = the evidence shows it; FALSE = the evidence shows its\n"
    "  absence; UNKNOWN = you examined the evidence and cannot tell; "
    "NOT_APPLICABLE\n"
    "  = the layer cannot apply to this medium.\n\n"
    "Concept selection:\n"
    "- For OBSERVED layers, list every concept the evidence supports in "
    '"concepts".\n'
    "  For FALSE/UNKNOWN/NOT_APPLICABLE layers, \"concepts\" is [].\n"
    "- Every concept needs a confidence in [0,1]. Report low-confidence concepts\n"
    "  too - they are kept and flagged, not dropped - so give an honest low\n"
    "  number rather than omitting a concept you are unsure of.\n"
    "- Every OBSERVED concept needs at least one evidence reference naming the\n"
    "  frame(s) that support it, as \"frame:<index>\" (frames are 0-indexed in the\n"
    "  order supplied).\n\n"
    "Controlled-vocabulary layers (visual inference IS allowed here):\n"
    "- For PEOPLE_ROLES, ANATOMY, TREATMENT_PROCEDURE, ACTIONS_EVENTS,\n"
    "  RELATIONSHIPS, CLINICAL_VISUAL_OBSERVATIONS and ENVIRONMENT, \"code\" MUST\n"
    "  be chosen from that layer's list below, copied EXACTLY, or the literal\n"
    "  value \"UNDETERMINED\".\n"
    "- You MAY infer from what you see; the term need not appear in supplied\n"
    "  text. But infer only to the specificity the evidence supports.\n"
    "- Use \"UNDETERMINED\" (with a confidence) when the layer clearly applies but\n"
    "  the specific code cannot be determined. Gloves, an instrument, a syringe,\n"
    "  a prepared scalp or physical contact show a procedure is underway but NOT\n"
    "  which named procedure - choose UNDETERMINED for TREATMENT_PROCEDURE in\n"
    "  that case rather than guessing a specific code.\n"
    "- NAMED-PROCEDURE RULE: only assert a specific TREATMENT_PROCEDURE code (for\n"
    "  example HAIR_TRANSPLANT_FUE, FUE_IMPLANTATION, INJECTABLES) when you are\n"
    "  confident (>= 0.7). If your confidence in the specific procedure is below\n"
    "  that, use UNDETERMINED. A named procedure is a clinical claim on a\n"
    "  patient record and must clear a higher bar than a generic concept.\n"
    "- Do not invent codes. Anything not in a list is either the closest listed\n"
    "  code (only if the evidence truly supports it) or UNDETERMINED.\n\n"
    "Open-vocabulary layers (the other 11):\n"
    "- There is no fixed list. \"code\" is a short UPPER_SNAKE_CASE phrase grounded\n"
    "  in the evidence (for example TREATMENT_ROOM_LIGHTING, VERTICAL_VIDEO).\n"
    "  Same confidence and evidence rules apply.\n\n"
)

VOCAB_HEADER = "Allowed concept codes by layer (copy a code EXACTLY, or use UNDETERMINED):\n"
EVIDENCE_HEADER = "\nEvidence follows.\n"


def _format_vocab(vocabulary: Mapping[str, Sequence[tuple[str, str]]]) -> str:
    blocks: list[str] = []
    for layer_id in CONTROLLED_LAYERS:
        pairs = list(vocabulary.get(layer_id, []))
        if not pairs:
            continue
        listed = "; ".join(
            f"{code} ({name})" if name and name != code else str(code)
            for code, name in pairs
        )
        blocks.append(f"{layer_id} ({len(pairs)} codes): {listed}")
    return "\n\n".join(blocks) + "\n"


def build_prompt(evidence_text: str,
                 vocabulary: Mapping[str, Sequence[tuple[str, str]]]) -> str:
    """Assemble the full v2 prompt with the current vocabularies injected.

    ``vocabulary`` maps each of the 7 controlled layer_ids to (code, name) pairs
    fetched from the live ontology / enum sets - never hard-coded here, so the
    prompt cannot go stale.  Validation should reject a run missing any of the 7.
    """
    header = CONTRACT_HEADER.replace("{layers}", ", ".join(LAYER_IDS))
    return header + VOCAB_HEADER + _format_vocab(vocabulary) + EVIDENCE_HEADER + evidence_text


def _humanize(code: str) -> str:
    return re.sub(r"[_\s]+", " ", str(code)).strip().title()


def finalize_concept(layer_id: str, concept: Mapping[str, Any],
                     resolver: OntologyResolver) -> dict[str, Any]:
    """Turn one raw model concept into a persistence row, deterministically.

    Applies the ontology resolver, the named-procedure confidence floor, and the
    low-confidence flag, and ALWAYS preserves the raw model output.  Returns the
    exact fields the Part C writer persists to asset_search_concepts_v2 plus its
    provenance columns.  Never drops the concept.
    """
    concept_type = _concept_type(layer_id)
    raw = str(concept.get("code", "")).strip()
    try:
        model_conf = float(concept.get("confidence"))
    except (TypeError, ValueError):
        model_conf = 0.0
    evidence = list(concept.get("evidence", []) or [])

    degraded = False
    if raw.upper() == UNDETERMINED:
        resolved_code, method, table = UNDETERMINED, "undetermined", None
    else:
        res = resolver.resolve(raw, concept_type)
        resolved_code, method, table = res.resolved_code, res.match_method, res.ontology_table
        # Named-procedure floor: a specific treatment below the floor degrades.
        if layer_id == NAMED_PROCEDURE_LAYER and model_conf < NAMED_PROCEDURE_CONFIDENCE_FLOOR:
            resolved_code, method, degraded = UNDETERMINED, "degraded_named_procedure", True
        elif resolved_code is None:
            resolved_code = None  # unresolved / no_ontology_domain: keep raw, flag below

    low_confidence = model_conf <= LOW_CONFIDENCE_THRESHOLD
    if method in ("undetermined", "degraded_named_procedure", "unresolved", "no_ontology_domain"):
        review_state = "AI_UNRESOLVED"
    elif low_confidence:
        review_state = "AI_LOW_CONFIDENCE"
    else:
        review_state = "AI_UNREVIEWED"

    canonical_code = resolved_code if resolved_code is not None else raw
    return {
        "concept_type": concept_type,
        "canonical_code": canonical_code,
        "display_text": _humanize(canonical_code if resolved_code else raw),
        "semantic_state": "OBSERVED",
        "confidence": model_conf,
        "review_state": review_state,
        "evidence": evidence,
        # provenance (raw model output, always kept and queryable per row)
        "raw_concept": raw,
        "model_confidence": model_conf,
        "resolution_method": method,
        "ontology_table": table,
        "low_confidence": low_confidence,
        "degraded": degraded,
    }


def apply_donor_precondition(concepts: list[dict]) -> list[dict]:
    """Asset-level rule, applied AFTER finalize_concept over all of an asset's
    concepts. A technique-level treatment code survives only if donor-site
    evidence is present on the same asset; otherwise it demotes to
    GENERIC_TREATMENT_FALLBACK with resolution_method 'degraded_no_donor_evidence'
    (queryable, like the 0.7-floor degrade). Preserves raw_concept. Mutates and
    returns the list. Never drops.
    """
    has_donor = any(c.get("canonical_code") in DONOR_EVIDENCE_CODES for c in concepts)
    if has_donor:
        return concepts
    for c in concepts:
        if c.get("concept_type") == "TREATMENT" and _is_technique_treatment(c.get("canonical_code", "")):
            if not c.get("raw_concept"):
                c["raw_concept"] = c["canonical_code"]
            c["canonical_code"] = GENERIC_TREATMENT_FALLBACK
            c["display_text"] = _humanize(GENERIC_TREATMENT_FALLBACK)
            c["resolution_method"] = "degraded_no_donor_evidence"
            c["degraded"] = True
    return concepts


__all__ = [
    "CONTRACT_VERSION", "LAYER_IDS", "STATES", "CONTROLLED_LAYERS",
    "LAYER_TO_CONCEPT_TYPE", "LOW_CONFIDENCE_THRESHOLD",
    "NAMED_PROCEDURE_CONFIDENCE_FLOOR", "TECHNIQUE_LEVEL_TREATMENTS",
    "DONOR_EVIDENCE_CODES", "UNDETERMINED",
    "build_prompt", "finalize_concept", "apply_donor_precondition",
]
