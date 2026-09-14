"""Ontology resolution layer.

Turns a raw model concept string into a *validated* ontology code, instead of
writing the model's wording verbatim (the current behaviour of
``canonical_rows._concept``).  This module resolves; it never drops.  An
unresolved concept is returned with ``resolved_code=None`` and
``match_method='unresolved'`` so the caller can persist it and so the operator
can see exactly what the model produces that the ontology does not yet cover.

Resolution order (first hit wins):

  1. ``exact``      - the raw code equals a ``code`` in the domain table
  2. ``alias``      - the raw text matches a ``treatment_aliases`` alias
                      (treatments only)
  3. ``normalized`` - case / underscore / plural-insensitive match against a
                      domain table's ``code`` or human name/label
  4. ``unresolved`` - nothing matched; the raw string is kept, flagged

Every result records the raw model output, the resolved code, which ontology
table it matched, and the match method - the audit trail the pipeline needs.

Domain tables (all keyed on ``code`` except ``treatment_aliases``):
  treatments (code,name), anatomy_terms (code,name), actions (code,name),
  clinical_observation_definitions (code,label), treatment_aliases
  (alias, normalized_alias -> treatment_id).

The concept_type recorded on ``asset_search_concepts_v2`` selects the domain:

  ANATOMY -> anatomy_terms   ACTION -> actions   TREATMENT -> treatments
  CLINICAL_OBSERVATION -> clinical_observation_definitions

Concept types with no controlled vocabulary (ROLE, RELATIONSHIP, ENVIRONMENT,
CONTENT_TYPE, OCR, SPOKEN_CONCEPT, SEMANTIC_CONCEPT) have no domain table; for
those the resolver reports ``no_ontology_domain`` unless an explicit domain is
requested.  This is deliberately distinct from ``unresolved`` (a code that
*should* have matched a domain but did not) so the coverage report can tell the
two apart.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

# concept_type -> ontology domain.  Four are DB tables keyed on `code`; two are
# fixed enums (CHECK-constraint value sets) that Job 6 already used, so their
# vocabulary is proven.  Seven controlled types in total (up from four).
DOMAIN_BY_TYPE: dict[str, str] = {
    "ANATOMY": "anatomy_terms",
    "ACTION": "actions",
    "TREATMENT": "treatments",
    "CLINICAL_OBSERVATION": "clinical_observation_definitions",
    "ENVIRONMENT": "locations",
    "ROLE": "person_roles",
    "RELATIONSHIP": "relationship_types",
}
# Fixed enum vocabularies (not DB tables): from the scene_people /
# scene_relationships CHECK constraints.
PERSON_ROLES: tuple[str, ...] = (
    "PATIENT", "DOCTOR", "CLINICIAN", "STAFF", "PRESENTER", "OTHER", "UNKNOWN",
)
RELATIONSHIP_TYPES: tuple[str, ...] = (
    "DOCTOR_CONSULTING_PATIENT", "DOCTOR_EXAMINING_PATIENT", "DOCTOR_MARKING_PATIENT",
    "DOCTOR_TREATING_PATIENT", "DOCTOR_INJECTING_PATIENT", "DOCTOR_EXPLAINING_TO_PATIENT",
    "PATIENT_LISTENING_TO_DOCTOR", "STAFF_ASSISTING_DOCTOR",
)
ENUM_DOMAINS: dict[str, tuple[str, ...]] = {
    "person_roles": PERSON_ROLES, "relationship_types": RELATIONSHIP_TYPES,
}
# When no concept_type domain applies, try these tables in order.
FALLBACK_DOMAINS: tuple[str, ...] = (
    "treatments", "anatomy_terms", "actions",
    "clinical_observation_definitions", "locations",
)
# Human-readable name column per table (clinical observations use `label`).
NAME_COLUMN: dict[str, str] = {
    "treatments": "name", "anatomy_terms": "name", "actions": "name",
    "clinical_observation_definitions": "label", "locations": "name",
}


def _canonical(text: str) -> str:
    """Uppercase, underscore-joined form (matches how codes are written)."""
    text = unicodedata.normalize("NFKC", str(text))
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def _singular(token: str) -> str:
    """Naive singulariser for a single lowercase token."""
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("ses"):
        return token[:-2]
    if len(token) > 2 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _normal_key(text: str) -> str:
    """Case / underscore / plural-insensitive comparison key.

    ``FRONTAL_SCALPS`` -> ``frontal scalp``; ``Lips`` -> ``lip``;
    ``visible-thinning`` -> ``visible thinning``.
    """
    text = unicodedata.normalize("NFKC", str(text)).lower()
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t]
    return " ".join(_singular(t) for t in tokens)


@dataclass(frozen=True)
class ResolutionResult:
    raw: str
    resolved_code: str | None
    ontology_table: str | None
    match_method: str  # exact | alias | normalized | unresolved | no_ontology_domain
    concept_type: str | None = None

    @property
    def resolved(self) -> bool:
        return self.resolved_code is not None


@dataclass
class _DomainIndex:
    table: str
    by_code: dict[str, str] = field(default_factory=dict)        # exact code -> code
    by_normal: dict[str, str] = field(default_factory=dict)      # normal key -> code

    def add(self, code: str, name: str | None) -> None:
        code = str(code)
        self.by_code[code] = code
        self.by_normal.setdefault(_normal_key(code), code)
        if name:
            self.by_normal.setdefault(_normal_key(name), code)


class OntologyResolver:
    """In-memory resolver built from ontology rows.

    Construct with :meth:`from_rows` (already-fetched rows) or
    :meth:`from_supabase` (fetches via the service-role client).  Keeping the
    fetch out of ``resolve`` means a batch run loads the ontology once.
    """

    def __init__(self, domains: Mapping[str, _DomainIndex],
                 alias_to_code: Mapping[str, str]) -> None:
        self._domains = dict(domains)
        self._alias_to_code = dict(alias_to_code)  # normal(alias) -> treatment code

    # ---- construction -----------------------------------------------------
    @classmethod
    def from_rows(
        cls,
        *,
        treatments: Iterable[Mapping],
        anatomy_terms: Iterable[Mapping],
        actions: Iterable[Mapping],
        clinical_observation_definitions: Iterable[Mapping],
        locations: Iterable[Mapping] = (),
        treatment_aliases: Iterable[Mapping] = (),
    ) -> "OntologyResolver":
        tables = {
            "treatments": treatments, "anatomy_terms": anatomy_terms,
            "actions": actions,
            "clinical_observation_definitions": clinical_observation_definitions,
            "locations": locations,
        }
        domains: dict[str, _DomainIndex] = {}
        code_by_id: dict[str, str] = {}
        for table, rows in tables.items():
            idx = _DomainIndex(table=table)
            name_col = NAME_COLUMN[table]
            for row in rows:
                code = row.get("code")
                if not code:
                    continue
                idx.add(code, row.get(name_col))
                if row.get("id") is not None:
                    code_by_id[str(row["id"])] = str(code)
            domains[table] = idx
        # Fixed enum vocabularies (code is its own display name).
        for enum_domain, values in ENUM_DOMAINS.items():
            idx = _DomainIndex(table=enum_domain)
            for code in values:
                idx.add(code, None)
            domains[enum_domain] = idx
        alias_to_code: dict[str, str] = {}
        for row in treatment_aliases:
            code = code_by_id.get(str(row.get("treatment_id")))
            if not code:
                continue
            for key in (row.get("alias"), row.get("normalized_alias")):
                if key:
                    alias_to_code.setdefault(_normal_key(key), code)
        return cls(domains, alias_to_code)

    @classmethod
    def from_supabase(cls, client) -> "OntologyResolver":
        def fetch(table: str, cols: str) -> list[dict]:
            return client.table(table).select(cols).eq("is_active", True).execute().data or []
        return cls.from_rows(
            treatments=fetch("treatments", "id,code,name"),
            anatomy_terms=fetch("anatomy_terms", "id,code,name"),
            actions=fetch("actions", "id,code,name"),
            clinical_observation_definitions=fetch(
                "clinical_observation_definitions", "id,code,label"),
            locations=fetch("locations", "id,code,name"),
            treatment_aliases=(client.table("treatment_aliases")
                               .select("treatment_id,alias,normalized_alias")
                               .eq("is_active", True).execute().data or []),
        )

    # ---- resolution -------------------------------------------------------
    def _domains_for(self, concept_type: str | None) -> tuple[str, ...]:
        if concept_type and concept_type in DOMAIN_BY_TYPE:
            return (DOMAIN_BY_TYPE[concept_type],)
        return ()

    def resolve(self, raw: str, concept_type: str | None = None) -> ResolutionResult:
        raw = "" if raw is None else str(raw)
        domains = self._domains_for(concept_type)
        # A concept type that maps to no controlled vocabulary: report distinctly.
        if concept_type is not None and not domains:
            return ResolutionResult(raw, None, None, "no_ontology_domain", concept_type)
        search = domains or FALLBACK_DOMAINS
        canon = _canonical(raw)
        # 1. exact code match
        for table in search:
            hit = self._domains[table].by_code.get(canon)
            if hit:
                return ResolutionResult(raw, hit, table, "exact", concept_type)
        # 2. alias lookup (treatments only)
        if "treatments" in search:
            hit = self._alias_to_code.get(_normal_key(raw))
            if hit:
                return ResolutionResult(raw, hit, "treatments", "alias", concept_type)
        # 3. normalized (case / underscore / plural) match
        nkey = _normal_key(raw)
        for table in search:
            hit = self._domains[table].by_normal.get(nkey)
            if hit:
                return ResolutionResult(raw, hit, table, "normalized", concept_type)
        # 4. no match - keep the raw string, flagged
        return ResolutionResult(raw, None, None, "unresolved", concept_type)


__all__ = ["OntologyResolver", "ResolutionResult", "DOMAIN_BY_TYPE"]
