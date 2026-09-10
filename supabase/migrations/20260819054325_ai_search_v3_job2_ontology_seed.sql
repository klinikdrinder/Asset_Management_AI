-- KDI AI Search V3 Job 2: idempotent controlled ontology seed.
-- No people/patient identities and no AI-generated concepts.

begin;

insert into public.treatments(code,name,parent_id,level,category,description)
values('HAIR_RESTORATION','Hair Restoration',null,0,'HAIR','Root controlled concept for hair restoration')
on conflict(code) do update set name=excluded.name,category=excluded.category,description=excluded.description;

insert into public.treatments(code,name,parent_id,level,category,description)
select 'HAIR_TRANSPLANT','Hair Transplant',id,1,'HAIR','Surgical hair restoration by transplantation'
from public.treatments where code='HAIR_RESTORATION'
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,level=excluded.level,category=excluded.category,description=excluded.description;

insert into public.treatments(code,name,parent_id,level,category,description)
select 'HAIR_TRANSPLANT_FUE','FUE',id,2,'HAIR_TRANSPLANT','Follicular unit extraction hair transplant'
from public.treatments where code='HAIR_TRANSPLANT'
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,level=excluded.level,category=excluded.category,description=excluded.description;

insert into public.treatments(code,name,parent_id,level,category)
select v.code,v.name,t.id,3,'FUE_WORKFLOW'
from public.treatments t
cross join (values
 ('FUE_CONSULTATION','Consultation'),
 ('FUE_HAIRLINE_DESIGN','Hairline Design'),
 ('FUE_DONOR_ASSESSMENT','Donor Assessment'),
 ('FUE_ANAESTHESIA','Anaesthesia'),
 ('FUE_EXTRACTION','Extraction'),
 ('FUE_GRAFT_PREPARATION','Graft Preparation'),
 ('FUE_IMPLANTATION','Implantation'),
 ('FUE_POST_OP','Post-op'),
 ('FUE_FOLLOW_UP','Follow-up')
) v(code,name)
where t.code='HAIR_TRANSPLANT_FUE'
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,level=excluded.level,category=excluded.category;

insert into public.treatment_aliases(treatment_id,alias,normalized_alias,alias_type,language)
select t.id,v.alias,lower(regexp_replace(btrim(v.alias),'\s+',' ','g')),'SYNONYM','en'
from (values
 ('FUE_HAIRLINE_DESIGN','hairline planning'),
 ('FUE_HAIRLINE_DESIGN','hairline drawing'),
 ('FUE_HAIRLINE_DESIGN','frontal hairline planning'),
 ('FUE_HAIRLINE_DESIGN','frontal design'),
 ('HAIR_TRANSPLANT_FUE','follicular unit extraction'),
 ('HAIR_TRANSPLANT_FUE','FUE transplant')
) v(treatment_code,alias)
join public.treatments t on t.code=v.treatment_code
on conflict(normalized_alias,language) do update set treatment_id=excluded.treatment_id,alias=excluded.alias,is_active=true;

insert into public.anatomy_terms(code,name,parent_id,domain)
values
 ('SCALP','Scalp',null,'HAIR_SCALP'),
 ('FACE','Face',null,'FACE'),
 ('NECK','Neck',null,'NECK')
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,domain=excluded.domain;

insert into public.anatomy_terms(code,name,parent_id,domain)
select v.code,v.name,p.id,v.domain
from (values
 ('FRONTAL_HAIRLINE','Frontal Hairline','SCALP','HAIR_SCALP'),
 ('FRONTAL_SCALP','Frontal Scalp','SCALP','HAIR_SCALP'),
 ('TEMPORAL_REGION','Temporal Region','SCALP','HAIR_SCALP'),
 ('MIDSCALP','Midscalp','SCALP','HAIR_SCALP'),
 ('CROWN','Crown','SCALP','HAIR_SCALP'),
 ('DONOR_REGION','Donor Region','SCALP','HAIR_SCALP'),
 ('RECIPIENT_REGION','Recipient Region','SCALP','HAIR_SCALP'),
 ('UPPER_FACE','Upper Face','FACE','FACE'),
 ('PERIOCULAR','Periocular','FACE','FACE'),
 ('MIDFACE','Midface','FACE','FACE'),
 ('LOWER_FACE','Lower Face','FACE','FACE')
) v(code,name,parent_code,domain)
join public.anatomy_terms p on p.code=v.parent_code
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,domain=excluded.domain;

insert into public.anatomy_terms(code,name,parent_id,domain)
select v.code,v.name,p.id,'FACE'
from (values
 ('FOREHEAD','Forehead','UPPER_FACE'),
 ('GLABELLA','Glabella','UPPER_FACE'),
 ('TEMPORAL_FACE','Temporal Face','UPPER_FACE'),
 ('UNDER_EYE','Under Eye','PERIOCULAR'),
 ('CROWS_FEET_REGION','Crow''s Feet Region','PERIOCULAR'),
 ('CHEEK','Cheek','MIDFACE'),
 ('NASOLABIAL_REGION','Nasolabial Region','MIDFACE'),
 ('LIPS','Lips','LOWER_FACE'),
 ('JAWLINE','Jawline','LOWER_FACE'),
 ('CHIN','Chin','LOWER_FACE'),
 ('SUBMENTAL_REGION','Submental Region','LOWER_FACE')
) v(code,name,parent_code)
join public.anatomy_terms p on p.code=v.parent_code
on conflict(code) do update set name=excluded.name,parent_id=excluded.parent_id,domain=excluded.domain;

insert into public.actions(code,name,category)
values
 ('CONSULTING','Consulting','COMMUNICATION'),
 ('DISCUSSING','Discussing','COMMUNICATION'),
 ('TALKING','Talking','COMMUNICATION'),
 ('LISTENING','Listening','COMMUNICATION'),
 ('EXPLAINING','Explaining','COMMUNICATION'),
 ('POINTING','Pointing','GESTURE'),
 ('EXAMINING','Examining','CLINICAL'),
 ('MARKING','Marking','CLINICAL'),
 ('DRAWING_HAIRLINE','Drawing Hairline','CLINICAL'),
 ('CLEANSING','Cleansing','CLINICAL'),
 ('INJECTING','Injecting','CLINICAL'),
 ('HOLDING_SYRINGE','Holding Syringe','CLINICAL'),
 ('USING_DEVICE','Using Device','CLINICAL'),
 ('CHECKING_SYMMETRY','Checking Symmetry','CLINICAL'),
 ('TOUCHING','Touching','GESTURE'),
 ('LOOKING_IN_MIRROR','Looking in Mirror','BEHAVIOUR'),
 ('SMILING','Smiling','BEHAVIOUR'),
 ('WALKING','Walking','MOVEMENT'),
 ('LYING_DOWN','Lying Down','POSITION'),
 ('EXTRACTING_GRAFTS','Extracting Grafts','FUE_PROCEDURE'),
 ('SORTING_GRAFTS','Sorting Grafts','FUE_PROCEDURE'),
 ('IMPLANTING_GRAFTS','Implanting Grafts','FUE_PROCEDURE')
on conflict(code) do update set name=excluded.name,category=excluded.category;

insert into public.locations(code,name,location_type,parent_id,is_verified)
values
 ('CLINIC','Clinic','GENERIC',null,false),
 ('OUTDOOR','Outdoor','GENERIC',null,false),
 ('HOME','Home','GENERIC',null,false),
 ('HOTEL','Hotel','GENERIC',null,false)
on conflict(code) do update set name=excluded.name,location_type=excluded.location_type,parent_id=excluded.parent_id,is_verified=excluded.is_verified;

insert into public.locations(code,name,location_type,parent_id,is_verified)
select v.code,v.name,'GENERIC',p.id,false
from (values
 ('CONSULTATION_ROOM','Consultation Room'),
 ('TREATMENT_ROOM','Treatment Room'),
 ('OPERATING_ROOM','Operating Room'),
 ('RECEPTION','Reception'),
 ('WAITING_AREA','Waiting Area'),
 ('CORRIDOR','Corridor'),
 ('OFFICE','Office')
) v(code,name)
join public.locations p on p.code='CLINIC'
on conflict(code) do update set name=excluded.name,location_type=excluded.location_type,parent_id=excluded.parent_id,is_verified=excluded.is_verified;

commit;


