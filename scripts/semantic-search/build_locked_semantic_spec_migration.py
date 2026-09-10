"""Build the additive SQL migration from the canonical repository JSON mirror."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "config" / "semantic-search" / "kdi_semantic_18_layer_v1.json"
MIGRATION_PATH = ROOT / "supabase" / "migrations" / "20260828011044_lock_kdi_semantic_18_layer_v1.sql"
DOC_PATH = ROOT / "docs" / "semantic-search" / "KDI_LOCKED_18_LAYER_SEMANTIC_STANDARD_V1.md"


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    fingerprint = spec["spec_fingerprint"]
    payload = dict(spec)
    payload.pop("spec_fingerprint")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != fingerprint:
        raise SystemExit("repository specification fingerprint mismatch")
    full_json = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    layer_values = []
    for layer in spec["layers"]:
        fields = [
            "kdi_semantic_18_layer_v1", layer["layer_id"], layer["layer_number"], layer["layer_name"],
            layer["description"], layer["purpose"], layer["applicability_rules"], layer["expected_information"],
            layer["allowed_semantic_states"], layer["evidence_requirements"], layer["completeness_rules"],
            layer["search_inclusion_rules"], layer["search_critical_fields"], layer["modality_dependencies"],
            layer["quality_rules"], layer["prohibited_inferences"], layer["fallback_behavior"], fingerprint,
        ]
        encoded = []
        for index, value in enumerate(fields):
            if index == 2:
                encoded.append(str(value))
            elif isinstance(value, list):
                encoded.append(sql_literal(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) + "::jsonb")
            else:
                encoded.append(sql_literal(str(value)))
        layer_values.append("(" + ",".join(encoded) + ",false,null)")
    layer_values_sql = ",\n".join(layer_values)
    sql = f"""begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';
create extension if not exists pgcrypto;

create table if not exists public.semantic_specifications (
  spec_version text primary key,
  display_version text not null unique,
  status text not null check (status in ('DRAFT','LOCKED','SUPERSEDED')),
  spec_content jsonb not null,
  canonical_content text not null,
  spec_fingerprint text not null unique check (spec_fingerprint ~ '^[0-9a-f]{{64}}$'),
  locked boolean not null default false,
  locked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  superseded_by text references public.semantic_specifications(spec_version),
  unique(spec_version,spec_fingerprint),
  check ((locked and status='LOCKED' and locked_at is not null) or (not locked and locked_at is null)),
  check (canonical_content::jsonb = spec_content - 'spec_fingerprint'),
  check (encode(digest(convert_to(canonical_content,'UTF8'),'sha256'),'hex') = spec_fingerprint)
);

create table if not exists public.semantic_layer_definition_versions (
  spec_version text not null references public.semantic_specifications(spec_version),
  layer_id text not null references public.semantic_layer_definitions(layer_id),
  layer_number smallint not null check (layer_number between 1 and 18),
  layer_name text not null,
  description text not null check (btrim(description) <> ''),
  purpose text not null check (btrim(purpose) <> ''),
  applicability_rules jsonb not null check (jsonb_typeof(applicability_rules)='array' and jsonb_array_length(applicability_rules)>0),
  expected_information jsonb not null check (jsonb_typeof(expected_information)='array' and jsonb_array_length(expected_information)>0),
  allowed_semantic_states jsonb not null check (jsonb_typeof(allowed_semantic_states)='array' and jsonb_array_length(allowed_semantic_states)>0),
  evidence_requirements jsonb not null check (jsonb_typeof(evidence_requirements)='array' and jsonb_array_length(evidence_requirements)>0),
  completeness_rules jsonb not null check (jsonb_typeof(completeness_rules)='array' and jsonb_array_length(completeness_rules)>0),
  search_inclusion_rules jsonb not null check (jsonb_typeof(search_inclusion_rules)='array' and jsonb_array_length(search_inclusion_rules)>0),
  search_critical_fields jsonb not null check (jsonb_typeof(search_critical_fields)='array' and jsonb_array_length(search_critical_fields)>0),
  modality_dependencies jsonb not null check (jsonb_typeof(modality_dependencies)='array' and jsonb_array_length(modality_dependencies)>0),
  quality_rules jsonb not null check (jsonb_typeof(quality_rules)='array' and jsonb_array_length(quality_rules)>0),
  prohibited_inferences jsonb not null check (jsonb_typeof(prohibited_inferences)='array' and jsonb_array_length(prohibited_inferences)>0),
  fallback_behavior text not null check (btrim(fallback_behavior) <> ''),
  spec_fingerprint text not null,
  locked boolean not null default false,
  locked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key(spec_version,layer_id), unique(spec_version,layer_number),
  foreign key(spec_version,spec_fingerprint) references public.semantic_specifications(spec_version,spec_fingerprint),
  check ((locked and locked_at is not null) or (not locked and locked_at is null))
);

create or replace function public.reject_locked_semantic_spec_mutation() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if old.locked then raise exception 'locked semantic specification % is immutable', old.spec_version using errcode='55000'; end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger semantic_specifications_locked_guard before update or delete on public.semantic_specifications
for each row execute function public.reject_locked_semantic_spec_mutation();

create or replace function public.reject_locked_semantic_layer_definition_mutation() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if old.locked or exists(select 1 from public.semantic_specifications s where s.spec_version=old.spec_version and s.locked) then
    raise exception 'locked semantic layer definition %.% is immutable', old.spec_version, old.layer_id using errcode='55000';
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger semantic_layer_definition_versions_locked_guard before update or delete on public.semantic_layer_definition_versions
for each row execute function public.reject_locked_semantic_layer_definition_mutation();

create or replace function public.protect_locked_semantic_layer_identity() returns trigger
language plpgsql set search_path = pg_catalog, public as $$
begin
  if exists(select 1 from public.semantic_layer_definition_versions v join public.semantic_specifications s using(spec_version) where v.layer_id=old.layer_id and s.locked)
     and (tg_op='DELETE' or new.layer_id is distinct from old.layer_id or new.layer_number is distinct from old.layer_number or new.layer_name is distinct from old.layer_name or new.description is distinct from old.description) then
    raise exception 'semantic layer identity % is referenced by a locked specification', old.layer_id using errcode='55000';
  end if;
  return case when tg_op='DELETE' then old else new end;
end $$;
create trigger semantic_layer_definitions_locked_identity_guard before update or delete on public.semantic_layer_definitions
for each row execute function public.protect_locked_semantic_layer_identity();

insert into public.semantic_specifications(spec_version,display_version,status,spec_content,canonical_content,spec_fingerprint,locked,locked_at,superseded_by)
values('kdi_semantic_18_layer_v1','KDI_SEMANTIC_18_LAYER_V1','DRAFT',{sql_literal(full_json)}::jsonb,{sql_literal(canonical)},{sql_literal(fingerprint)},false,null,null);

insert into public.semantic_layer_definition_versions(
 spec_version,layer_id,layer_number,layer_name,description,purpose,applicability_rules,expected_information,
 allowed_semantic_states,evidence_requirements,completeness_rules,search_inclusion_rules,search_critical_fields,
 modality_dependencies,quality_rules,prohibited_inferences,fallback_behavior,spec_fingerprint,locked,locked_at)
values
{layer_values_sql};

update public.semantic_layer_definitions d set description=v.description
from public.semantic_layer_definition_versions v
where v.spec_version='kdi_semantic_18_layer_v1' and v.layer_id=d.layer_id and d.description='';

update public.semantic_layer_definition_versions set locked=true,locked_at=now(),updated_at=now()
where spec_version='kdi_semantic_18_layer_v1';
update public.semantic_specifications set status='LOCKED',locked=true,locked_at=now(),updated_at=now()
where spec_version='kdi_semantic_18_layer_v1';

alter table public.semantic_specifications enable row level security;
alter table public.semantic_layer_definition_versions enable row level security;
create policy semantic_specifications_read on public.semantic_specifications for select to authenticated using(locked);
create policy semantic_layer_definition_versions_read on public.semantic_layer_definition_versions for select to authenticated using(locked);
revoke insert,update,delete on public.semantic_specifications,public.semantic_layer_definition_versions from anon,authenticated;
grant select on public.semantic_specifications,public.semantic_layer_definition_versions to authenticated;
comment on table public.semantic_specifications is 'Canonical version registry for immutable semantic extraction specifications.';
comment on table public.semantic_layer_definition_versions is 'Versioned rich semantic layer definitions; locked versions are immutable.';
commit;
"""
    MIGRATION_PATH.write_text(sql, encoding="utf-8", newline="\n")
    DOC_PATH.write_text(
        "# KDI Locked 18-Layer Semantic Standard V1\n\n"
        "Status: `LOCKED`  \nSpec version: `kdi_semantic_18_layer_v1`  \n"
        f"SHA-256: `{fingerprint}`\n\n"
        "Supabase `semantic_specifications.spec_content` is the production canonical copy. "
        "The JSON below is the exact version-controlled mirror stored there. The fingerprint omits only "
        "the top-level `spec_fingerprint` field and hashes the canonical serialization described in the JSON.\n\n"
        "```json\n" + json.dumps(spec, indent=2, ensure_ascii=False) + "\n```\n",
        encoding="utf-8", newline="\n"
    )
    print(MIGRATION_PATH)


if __name__ == "__main__":
    main()
