-- KDI AI Search V3 Job 9: ontology expansion from the approved rich semantic architecture.

insert into public.semantic_layer_catalog(layer_code,layer_order,layer_name,scope,required_by_default,description) values
('TECHNICAL_METADATA',1,'Asset / Technical Metadata','ALL',true,'File, capture, format, orientation, duration, camera and technical quality.'),
('IDENTITY',2,'Identity','OPTIONAL',false,'Authorized known-person identity links and reference identity evidence.'),
('PERSON_APPEARANCE',3,'Person Appearance','ALL',true,'Per-visible-person age range, apparent gender, hair, face, wardrobe and appearance attributes.'),
('CLINICAL_VISUAL',4,'Clinical Visual','ALL',true,'AI-visible clinical observations separated from medically verified facts.'),
('AESTHETIC_FACIAL',5,'Aesthetic / Facial Concern','ALL',true,'Reusable facial concern observations with side, prominence, confidence and provenance.'),
('TREATMENT',6,'Procedure / Treatment','ALL',true,'Controlled treatment ontology and procedure-stage links.'),
('ACTION',7,'Action','ALL',true,'What each person is doing, including target anatomy or treatment.'),
('RELATIONSHIP',8,'Doctor–Patient Relationship','ALL',true,'Interactions between participants such as consulting, examining and treating.'),
('ENVIRONMENT',9,'Scene / Environment','ALL',true,'Clinic room, setting, indoor/outdoor, premium/clinical impression and location.'),
('CINEMATOGRAPHY',10,'Shot / Cinematography','ALL',true,'Shot size, angle, motion, focus, depth of field, lighting and style.'),
('COMPOSITION',11,'Composition','ALL',true,'Subject placement, headroom, negative space, text-safe areas, clutter and logo visibility.'),
('MARKETING_STORY',12,'Marketing / Storytelling','ALL',true,'Marketing role, funnel stage, hooks, topics, suggested use and platform suitability.'),
('SEMANTIC_NARRATIVE',13,'Semantic Narrative','ALL',true,'Literal, clinical-visual, storytelling, marketing and emotional natural-language interpretations.'),
('VIDEO_TIMELINE',14,'Video Scene Timeline','VIDEO',true,'Semantic scene segmentation with exact start/end timestamps.'),
('KEYFRAMES',15,'Keyframes','ALL',true,'Representative frames with exact timestamp/frame location and visual description.'),
('AUDIO_TRANSCRIPT',16,'Audio / Transcript','VIDEO_AUDIO',true,'Speech-to-text, speaker, language, topics and exact timing.'),
('OCR',17,'OCR','ALL',true,'Visible text, device names, signs, labels, cards and captions.'),
('EMBEDDINGS',18,'Multimodal Embeddings','ALL',true,'Multiple visual, identity, clinical, action, scene, marketing, narrative, audio and OCR embeddings.')
on conflict (layer_code) do update set
 layer_order=excluded.layer_order, layer_name=excluded.layer_name, scope=excluded.scope,
 required_by_default=excluded.required_by_default, description=excluded.description, updated_at=now();

insert into public.relationship_types(code,name,category,description) values
('DOCTOR_CONSULTING_PATIENT','Doctor Consulting Patient','CLINICAL_INTERACTION','Doctor and patient engaged in consultation.'),
('DOCTOR_EXAMINING_PATIENT','Doctor Examining Patient','CLINICAL_INTERACTION','Doctor visually or physically assessing the patient or treatment area.'),
('DOCTOR_TREATING_PATIENT','Doctor Treating Patient','CLINICAL_INTERACTION','Doctor actively performing a treatment or procedure on the patient.'),
('DOCTOR_EXPLAINING_TO_PATIENT','Doctor Explaining to Patient','COMMUNICATION','Doctor explaining concern, anatomy, treatment, result or aftercare.'),
('PATIENT_LISTENING_TO_DOCTOR','Patient Listening to Doctor','COMMUNICATION','Patient listening or responding to doctor guidance.'),
('STAFF_ASSISTING_DOCTOR','Staff Assisting Doctor','TEAM_INTERACTION','Clinical staff assisting the doctor.'),
('STAFF_ASSISTING_PATIENT','Staff Assisting Patient','TEAM_INTERACTION','Staff assisting or preparing the patient.'),
('PATIENT_VIEWING_RESULT','Patient Viewing Result','PATIENT_EXPERIENCE','Patient viewing result, mirror, before/after or treatment area.')
on conflict (code) do nothing;

-- Additional actions needed by the richer content-creator ontology.
insert into public.actions(code,name,category,description) values
('SITTING','Sitting','POSITION','Subject is seated.'),
('STANDING','Standing','POSITION','Subject is standing.'),
('TURNING','Turning','MOVEMENT','Subject turns head or body.'),
('RAISING_EYEBROWS','Raising Eyebrows','BEHAVIOUR','Patient raises eyebrows to expose dynamic forehead lines.'),
('VIEWING_MIRROR','Viewing Mirror','BEHAVIOUR','Patient views treatment area or result in a mirror.'),
('PREPARING_SYRINGE','Preparing Syringe','CLINICAL','Doctor or clinician prepares a syringe.'),
('PREPARING_PATIENT','Preparing Patient','CLINICAL','Staff or doctor prepares patient before procedure.'),
('SHAVING_DONOR','Shaving Donor Region','FUE_PROCEDURE','Donor area is being shaved or trimmed.'),
('ASSESSING_DONOR','Assessing Donor Region','FUE_PROCEDURE','Donor area is being examined or assessed.'),
('PHOTOGRAPHING','Photographing','DOCUMENTATION','Taking clinical or marketing photographs.'),
('RECORDING_VIDEO','Recording Video','DOCUMENTATION','Recording patient, procedure or testimonial footage.')
on conflict (code) do nothing;

-- Additional reusable facial/anatomical regions.
insert into public.anatomy_terms(code,name,parent_id,domain,description) values
('BROW','Brow',(select id from public.anatomy_terms where code='UPPER_FACE'),'FACE','Eyebrow/brow region.'),
('TEAR_TROUGH','Tear Trough',(select id from public.anatomy_terms where code='UNDER_EYE'),'FACE','Tear trough region.'),
('EYE_BAG_REGION','Eye Bag Region',(select id from public.anatomy_terms where code='UNDER_EYE'),'FACE','Lower eyelid/eye bag region.'),
('MARIONETTE_REGION','Marionette Region',(select id from public.anatomy_terms where code='LOWER_FACE'),'FACE','Marionette line region.'),
('MASSETER_REGION','Masseter Region',(select id from public.anatomy_terms where code='LOWER_FACE'),'FACE','Masseter/jaw muscle region.'),
('NOSE','Nose',(select id from public.anatomy_terms where code='FACE'),'FACE','Nose region.'),
('BUNNY_LINE_REGION','Bunny Line Region',(select id from public.anatomy_terms where code='NOSE'),'FACE','Lateral nasal bunny-line region.')
on conflict (code) do nothing;

-- Treatment ontology beyond the initial FUE-only branch.
insert into public.treatments(code,name,parent_id,level,category,description) values
('AESTHETICS','Aesthetics',null,0,'AESTHETICS','Aesthetic medicine treatment family'),
('INJECTABLES','Injectables',(select id from public.treatments where code='AESTHETICS'),1,'AESTHETICS','Injectable aesthetic treatments'),
('BOTULINUM_TOXIN','Botulinum Toxin',(select id from public.treatments where code='INJECTABLES'),2,'INJECTABLES','Botulinum toxin treatment'),
('DERMAL_FILLER','Dermal Filler',(select id from public.treatments where code='INJECTABLES'),2,'INJECTABLES','Dermal filler treatment'),
('SKIN_BOOSTER','Skin Booster',(select id from public.treatments where code='INJECTABLES'),2,'INJECTABLES','Skin booster treatment'),
('ENERGY_BASED','Energy Based Treatments',(select id from public.treatments where code='AESTHETICS'),1,'AESTHETICS','Energy-based facial and body treatments'),
('RF_TIGHTENING','RF Tightening',(select id from public.treatments where code='ENERGY_BASED'),2,'ENERGY_BASED','Radiofrequency tightening'),
('LASER','Laser',(select id from public.treatments where code='ENERGY_BASED'),2,'ENERGY_BASED','Laser treatment family'),
('PICO_LASER','Pico Laser',(select id from public.treatments where code='LASER'),3,'LASER','Pico laser treatment'),
('HIFU','HIFU',(select id from public.treatments where code='ENERGY_BASED'),2,'ENERGY_BASED','High-intensity focused ultrasound'),
('XERF','XERF',(select id from public.treatments where code='ENERGY_BASED'),2,'ENERGY_BASED','XERF treatment'),
('THERMAGE','Thermage',(select id from public.treatments where code='ENERGY_BASED'),2,'ENERGY_BASED','Thermage treatment'),
('SKIN_TREATMENTS','Skin Treatments',(select id from public.treatments where code='AESTHETICS'),1,'AESTHETICS','Skin treatment family'),
('MICRONEEDLING','Microneedling',(select id from public.treatments where code='SKIN_TREATMENTS'),2,'SKIN_TREATMENTS','Microneedling treatment'),
('ACNE_TREATMENT','Acne Treatment',(select id from public.treatments where code='SKIN_TREATMENTS'),2,'SKIN_TREATMENTS','Acne-focused treatment'),
('FACIAL','Facial',(select id from public.treatments where code='SKIN_TREATMENTS'),2,'SKIN_TREATMENTS','Facial treatment'),
('HAIR_PRP','Hair PRP',(select id from public.treatments where code='HAIR_RESTORATION'),1,'HAIR','Platelet-rich plasma for hair restoration')
on conflict (code) do nothing;

-- Botulinum subtypes need the parent created above; insert separately.
insert into public.treatments(code,name,parent_id,level,category,description) values
('BOTULINUM_FOREHEAD','Botulinum Toxin - Forehead',(select id from public.treatments where code='BOTULINUM_TOXIN'),3,'BOTULINUM_TOXIN','Forehead botulinum toxin'),
('BOTULINUM_GLABELLA','Botulinum Toxin - Glabella',(select id from public.treatments where code='BOTULINUM_TOXIN'),3,'BOTULINUM_TOXIN','Glabellar botulinum toxin'),
('BOTULINUM_CROWS_FEET','Botulinum Toxin - Crow''s Feet',(select id from public.treatments where code='BOTULINUM_TOXIN'),3,'BOTULINUM_TOXIN','Lateral periocular botulinum toxin'),
('BOTULINUM_MASSETER','Botulinum Toxin - Masseter',(select id from public.treatments where code='BOTULINUM_TOXIN'),3,'BOTULINUM_TOXIN','Masseter botulinum toxin'),
('BOTULINUM_BUNNY_LINES','Botulinum Toxin - Bunny Lines',(select id from public.treatments where code='BOTULINUM_TOXIN'),3,'BOTULINUM_TOXIN','Bunny-line botulinum toxin')
on conflict (code) do nothing;

-- Clinical visual ontology: AI-visible observations and clinician-only facts are explicitly separated.
insert into public.clinical_observation_definitions(code,domain,label,anatomy_code,value_kind,ai_observable,requires_clinician_verification,description) values
('HAIRLINE_VISIBLE','HAIR','Hairline visible','FRONTAL_HAIRLINE','BOOLEAN',true,false,'Whether frontal hairline is visibly assessable.'),
('HAIRLINE_SHAPE','HAIR','Hairline shape','FRONTAL_HAIRLINE','TEXT',true,false,'Visible hairline shape description.'),
('TEMPORAL_RECESSION_VISIBLE','HAIR','Temporal recession visible','TEMPORAL_REGION','BOOLEAN',true,false,'Visible temporal recession.'),
('FRONTAL_THINNING_VISIBLE','HAIR','Frontal thinning visible','FRONTAL_SCALP','BOOLEAN',true,false,'Visible frontal scalp thinning.'),
('MIDSCALP_THINNING_VISIBLE','HAIR','Midscalp thinning visible','MIDSCALP','BOOLEAN',true,false,'Visible midscalp thinning.'),
('CROWN_THINNING_VISIBLE','HAIR','Crown thinning visible','CROWN','BOOLEAN',true,false,'Visible crown thinning.'),
('DIFFUSE_THINNING_VISIBLE','HAIR','Diffuse thinning visible','SCALP','BOOLEAN',true,false,'Diffuse visible reduction in density.'),
('SCALP_VISIBILITY','HAIR','Scalp visibility','SCALP','TEXT',true,false,'Degree/description of scalp visibility through hair.'),
('HAIR_DENSITY_VISUAL','HAIR','Hair density visual','SCALP','TEXT',true,false,'Visual density impression, not measured density.'),
('HAIR_CALIBRE_VISUAL','HAIR','Hair calibre visual','SCALP','TEXT',true,false,'Visual hair calibre impression.'),
('GREY_HAIR_PERCENT_ESTIMATE','HAIR','Grey hair percentage estimate','SCALP','NUMBER',true,false,'Approximate visible grey hair percentage.'),
('DONOR_REGION_VISIBLE','HAIR','Donor region visible','DONOR_REGION','BOOLEAN',true,false,'Whether donor region is visible.'),
('RECIPIENT_REGION_VISIBLE','HAIR','Recipient region visible','RECIPIENT_REGION','BOOLEAN',true,false,'Whether recipient region is visible.'),
('PRE_TRANSPLANT_VISUAL','HAIR','Pre-transplant visual stage','SCALP','BOOLEAN',true,false,'Visual evidence consistent with pre-procedure documentation.'),
('DURING_TRANSPLANT_VISUAL','HAIR','During-transplant visual stage','SCALP','BOOLEAN',true,false,'Visual evidence of active transplant procedure.'),
('POST_TRANSPLANT_VISUAL','HAIR','Post-transplant visual stage','SCALP','BOOLEAN',true,false,'Visual evidence consistent with immediate/short-term post procedure.'),
('GRAFT_SITES_VISIBLE','HAIR','Graft sites visible','RECIPIENT_REGION','BOOLEAN',true,false,'Visible recipient graft sites.'),
('EXTRACTION_SITES_VISIBLE','HAIR','Extraction sites visible','DONOR_REGION','BOOLEAN',true,false,'Visible donor extraction sites.'),
('REDNESS_VISIBLE','HAIR','Redness visible','SCALP','BOOLEAN',true,false,'Visible redness.'),
('CRUSTING_VISIBLE','HAIR','Crusting visible','SCALP','BOOLEAN',true,false,'Visible crusting.'),
('NORWOOD_GRADE_VERIFIED','HAIR','Norwood grade verified','SCALP','ENUM',false,true,'Clinician-verified Norwood grade; must not be inferred as diagnosis.'),
('GRAFT_COUNT_VERIFIED','HAIR','Graft count verified','SCALP','NUMBER',false,true,'Verified graft count from clinical record.'),
('PROCEDURE_VERIFIED','HAIR','Procedure verified','SCALP','TEXT',false,true,'Clinician or source-record verified procedure.'),
('DIAGNOSIS_VERIFIED','HAIR','Diagnosis verified','SCALP','TEXT',false,true,'Clinician-verified diagnosis.'),
('FOREHEAD_LINES_VISIBLE','AESTHETIC_FACE','Forehead lines visible','FOREHEAD','BOOLEAN',true,false,'Visible forehead lines.'),
('GLABELLAR_LINES_VISIBLE','AESTHETIC_FACE','Glabellar lines visible','GLABELLA','BOOLEAN',true,false,'Visible glabellar lines.'),
('BROW_POSITION','AESTHETIC_FACE','Brow position','BROW','TEXT',true,false,'Visible brow position.'),
('BROW_ASYMMETRY','AESTHETIC_FACE','Brow asymmetry','BROW','TEXT',true,false,'Visible brow asymmetry.'),
('TEMPORAL_HOLLOWING','AESTHETIC_FACE','Temporal hollowing','TEMPORAL_FACE','TEXT',true,false,'Visible temporal hollowing.'),
('CROWS_FEET_VISIBLE','AESTHETIC_FACE','Crow''s feet visible','CROWS_FEET_REGION','BOOLEAN',true,false,'Visible lateral periocular lines.'),
('UNDER_EYE_LINES','AESTHETIC_FACE','Under-eye lines','UNDER_EYE','TEXT',true,false,'Visible under-eye lines.'),
('TEAR_TROUGH_VISIBLE','AESTHETIC_FACE','Tear trough visible','TEAR_TROUGH','TEXT',true,false,'Visible tear trough prominence.'),
('EYE_BAGS_VISIBLE','AESTHETIC_FACE','Eye bags visible','EYE_BAG_REGION','TEXT',true,false,'Visible eye bags/lower lid fullness.'),
('DARK_CIRCLE_VISIBILITY','AESTHETIC_FACE','Dark circle visibility','UNDER_EYE','TEXT',true,false,'Visible dark circle prominence.'),
('CHEEK_VOLUME','AESTHETIC_FACE','Cheek volume','CHEEK','TEXT',true,false,'Visible cheek volume impression.'),
('NASOLABIAL_FOLD_VISIBILITY','AESTHETIC_FACE','Nasolabial fold visibility','NASOLABIAL_REGION','TEXT',true,false,'Visible nasolabial fold prominence.'),
('PIGMENTATION_VISIBLE','AESTHETIC_FACE','Pigmentation visible','FACE','TEXT',true,false,'Visible pigmentation.'),
('ACNE_VISIBLE','AESTHETIC_FACE','Acne visible','FACE','TEXT',true,false,'Visible acne lesions.'),
('ACNE_SCARRING_VISIBLE','AESTHETIC_FACE','Acne scarring visible','FACE','TEXT',true,false,'Visible acne scarring.'),
('PORES_VISIBLE','AESTHETIC_FACE','Pore visibility','FACE','TEXT',true,false,'Visible pore prominence.'),
('SKIN_TEXTURE_VISUAL','AESTHETIC_FACE','Skin texture visual','FACE','TEXT',true,false,'Visual skin texture impression.'),
('MARIONETTE_LINES_VISIBLE','AESTHETIC_FACE','Marionette lines visible','MARIONETTE_REGION','TEXT',true,false,'Visible marionette lines.'),
('LIP_VOLUME_VISUAL','AESTHETIC_FACE','Lip volume visual','LIPS','TEXT',true,false,'Visible lip volume impression.'),
('JAWLINE_DEFINITION','AESTHETIC_FACE','Jawline definition','JAWLINE','TEXT',true,false,'Visible jawline definition.'),
('JOWLING_VISIBLE','AESTHETIC_FACE','Jowling visible','LOWER_FACE','TEXT',true,false,'Visible jowling.'),
('CHIN_PROJECTION_VISUAL','AESTHETIC_FACE','Chin projection visual','CHIN','TEXT',true,false,'Visible chin projection impression.'),
('DOUBLE_CHIN_VISIBLE','AESTHETIC_FACE','Double chin visible','SUBMENTAL_REGION','TEXT',true,false,'Visible submental fullness/double chin.'),
('SKIN_LAXITY_VISIBLE','AESTHETIC_FACE','Skin laxity visible','FACE','TEXT',true,false,'Visible skin laxity.'),
('NECK_LINES_VISIBLE','AESTHETIC_FACE','Neck lines visible','NECK','TEXT',true,false,'Visible neck lines.'),
('NECK_LAXITY_VISIBLE','AESTHETIC_FACE','Neck laxity visible','NECK','TEXT',true,false,'Visible neck laxity.'),
('SUBMENTAL_FULLNESS','AESTHETIC_FACE','Submental fullness','SUBMENTAL_REGION','TEXT',true,false,'Visible submental fullness.')
on conflict (code) do update set
 domain=excluded.domain,label=excluded.label,anatomy_code=excluded.anatomy_code,value_kind=excluded.value_kind,
 ai_observable=excluded.ai_observable,requires_clinician_verification=excluded.requires_clinician_verification,
 description=excluded.description,is_active=true,updated_at=now();
;
