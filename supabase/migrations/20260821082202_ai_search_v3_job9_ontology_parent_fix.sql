-- Fix parent links for ontology rows inserted in the same prior statement snapshot.
update public.treatments set parent_id=(select id from public.treatments where code='AESTHETICS'),updated_at=now()
where code in ('INJECTABLES','ENERGY_BASED','SKIN_TREATMENTS');
update public.treatments set parent_id=(select id from public.treatments where code='INJECTABLES'),updated_at=now()
where code in ('BOTULINUM_TOXIN','DERMAL_FILLER','SKIN_BOOSTER');
update public.treatments set parent_id=(select id from public.treatments where code='ENERGY_BASED'),updated_at=now()
where code in ('RF_TIGHTENING','LASER','HIFU','XERF','THERMAGE');
update public.treatments set parent_id=(select id from public.treatments where code='SKIN_TREATMENTS'),updated_at=now()
where code in ('MICRONEEDLING','ACNE_TREATMENT','FACIAL');
update public.treatments set parent_id=(select id from public.treatments where code='LASER'),updated_at=now()
where code='PICO_LASER';
update public.anatomy_terms set parent_id=(select id from public.anatomy_terms where code='NOSE'),updated_at=now()
where code='BUNNY_LINE_REGION';;
