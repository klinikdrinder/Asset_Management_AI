# KDI Locked 18-Layer Semantic Standard V1

Status: `LOCKED`  
Spec version: `kdi_semantic_18_layer_v1`  
SHA-256: `6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7`

Supabase `semantic_specifications.spec_content` is the production canonical copy. The JSON below is the exact version-controlled mirror stored there. The fingerprint omits only the top-level `spec_fingerprint` field and hashes the canonical serialization described in the JSON.

```json
{
  "spec_version": "kdi_semantic_18_layer_v1",
  "display_version": "KDI_SEMANTIC_18_LAYER_V1",
  "status": "LOCKED",
  "global_rules": {
    "semantic_states": {
      "allowed": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "OBSERVED": "Reliable evidence supports the proposition.",
      "FALSE": "Reliable evidence explicitly supports the proposition being false; it never means the model did not see it.",
      "UNKNOWN": "Insufficient reliable evidence exists to determine the proposition.",
      "NOT_APPLICABLE": "The question or modality does not apply to the asset or layer and is not an extraction failure.",
      "invariants": [
        "UNKNOWN != FALSE",
        "ABSENCE OF EVIDENCE IS NOT EVIDENCE OF ABSENCE"
      ]
    },
    "modality_fallback": {
      "rule": "INDEX FROM ALL RELIABLE AVAILABLE MODALITIES.",
      "modalities": [
        "technical/file metadata",
        "visual observations",
        "scene/event structure",
        "speech/audio",
        "OCR/visible text",
        "structured semantic assertions",
        "semantic narrative",
        "trusted metadata/context",
        "derived search representations",
        "embeddings"
      ],
      "missing_modalities_block_indexing": false,
      "single_primary_field_required": false
    },
    "no_audio": "If an asset has no audio track, SPEECH_TRANSCRIPT_AUDIO is NOT_APPLICABLE. Do not invent transcript, language, or speaker; do not mark extraction failed or block indexing. If audio exists but speech is not understandable, transcript/language facts are UNKNOWN or an observed no-intelligible-speech fact when supported.",
    "no_visible_text": "If no visible text exists, OCR_VISIBLE_TEXT is NOT_APPLICABLE. If text appears present but cannot be read reliably, OCR_VISIBLE_TEXT is UNKNOWN. Never hallucinate text and never let OCR failure block visual indexing.",
    "blurry_low_quality": "Record supported quality evidence such as blur, motion blur, low resolution, poor exposure, occlusion, or unstable camera. Store only semantic facts that remain supportable. Never guess treatment, anatomy, role, identity, action, or clinical condition from a blurry medical-looking scene.",
    "evidence_trust_guidance": [
      "deterministic asset identity / technical metadata",
      "direct structured semantic observations",
      "scene/event evidence",
      "trusted normalized semantic evidence",
      "semantic narrative grounded in evidence",
      "accepted transcript evidence",
      "accepted OCR evidence",
      "semantic text similarity",
      "visual similarity"
    ],
    "evidence_trust_guidance_is_override_rule": false,
    "canonical_search_document": "Combine trusted available structured 18-layer evidence, master/global description, scene/event facts, accepted transcript, accepted OCR, safe metadata, search concepts, and embeddings. Audio, OCR, treatment classification, person identity, and every other single modality are optional.",
    "completeness": "Completeness answers whether the layer fully evaluated all applicable requirements in this locked specification; it does not measure the number of positive facts. COMPLETE may contain UNKNOWN, NOT_APPLICABLE, or zero positive assertions. Processing status and completeness status are independent and completeness must be actively computed rather than left at an insertion default.",
    "processing_status": [
      "PENDING",
      "RUNNING",
      "COMPLETE",
      "FAILED"
    ],
    "completeness_status": [
      "COMPLETE",
      "PARTIAL",
      "NOT_EVALUATED"
    ],
    "future_run_contract": "Before analysis begins, a worker must resolve and record semantic_spec_version and semantic_spec_fingerprint, and fail closed when its expected values do not match the locked canonical specification."
  },
  "layers": [
    {
      "layer_number": 1,
      "layer_id": "ASSET_IDENTITY_PROVENANCE",
      "layer_name": "Asset Identity & Provenance",
      "description": "Identify the canonical asset and deterministic source/provenance information needed to trace the file.",
      "purpose": "Trace identity and lineage without semantic guessing.",
      "applicability_rules": [
        "Applies to every asset",
        "Uses deterministic metadata"
      ],
      "expected_information": [
        "canonical asset ID",
        "filename",
        "extension",
        "media type",
        "MIME type",
        "file size",
        "dimensions",
        "duration",
        "source system",
        "source folder",
        "source file reference",
        "destination reference",
        "checksums/hashes",
        "ingestion timestamp",
        "modification timestamp",
        "analysis version",
        "provenance lineage"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Deterministic file, source-system, or ingestion records",
        "Valid provenance linkage"
      ],
      "completeness_rules": [
        "COMPLETE when all applicable required deterministic fields available to the pipeline were evaluated and provenance linkage is valid",
        "Unavailable optional metadata alone does not make the layer PARTIAL"
      ],
      "search_inclusion_rules": [
        "Include filename, media type, safe technical metadata, and appropriate provenance fields"
      ],
      "search_critical_fields": [
        "canonical asset ID",
        "filename",
        "media type",
        "checksums/hashes"
      ],
      "modality_dependencies": [
        "technical/file metadata"
      ],
      "quality_rules": [
        "Metadata availability is evaluated independently of visual or audio quality"
      ],
      "prohibited_inferences": [
        "Do not infer semantic content from filename unless separately labeled metadata-derived inference"
      ],
      "fallback_behavior": "Preserve known deterministic facts and mark genuinely indeterminate applicable facts UNKNOWN."
    },
    {
      "layer_number": 2,
      "layer_id": "GLOBAL_ASSET_UNDERSTANDING",
      "layer_name": "Global Asset Understanding",
      "description": "Provide a concise evidence-grounded understanding of the whole asset.",
      "purpose": "Summarize primary content, activity, setting, purpose, and uncertainty.",
      "applicability_rules": [
        "Applies to every usable asset",
        "Videos use representative scene/event evidence",
        "Images use full-frame evidence"
      ],
      "expected_information": [
        "primary visible subject/content",
        "main activity",
        "broad setting",
        "overall media purpose where supportable",
        "general clinical/non-clinical context",
        "short description",
        "master description",
        "uncertainty"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Claims must link to reliable whole-frame or representative scene/event evidence"
      ],
      "completeness_rules": [
        "COMPLETE when all applicable global categories were evaluated, including explicit UNKNOWN where evidence is insufficient"
      ],
      "search_inclusion_rules": [
        "HIGH contribution from grounded global descriptions and categories"
      ],
      "search_critical_fields": [
        "primary content",
        "main activity",
        "setting",
        "short description",
        "master description"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "trusted metadata/context"
      ],
      "quality_rules": [
        "Low-quality evidence narrows claims rather than forcing PARTIAL"
      ],
      "prohibited_inferences": [
        "Do not invent treatment, identity, diagnosis, or intent"
      ],
      "fallback_behavior": "Build the best grounded global account from all reliable available modalities."
    },
    {
      "layer_number": 3,
      "layer_id": "TEMPORAL_SCENE_STRUCTURE",
      "layer_name": "Temporal / Scene Structure",
      "description": "Represent time-based organization of video assets.",
      "purpose": "Support temporal evidence and scene-level retrieval.",
      "applicability_rules": [
        "Applies to video",
        "Still images are NOT_APPLICABLE"
      ],
      "expected_information": [
        "scene boundaries",
        "start/end time",
        "scene order",
        "keyframes",
        "event windows",
        "supported temporal transitions"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Full usable video duration evaluated under the locked segmentation policy"
      ],
      "completeness_rules": [
        "Video is COMPLETE when temporal analysis successfully covers full usable duration",
        "Still image is NOT_APPLICABLE rather than PARTIAL"
      ],
      "search_inclusion_rules": [
        "Include scene-level retrieval and temporal evidence"
      ],
      "search_critical_fields": [
        "scene boundaries",
        "timestamps",
        "event windows"
      ],
      "modality_dependencies": [
        "scene/event structure",
        "visual observations"
      ],
      "quality_rules": [
        "Unusable intervals may be UNKNOWN with explicit quality evidence"
      ],
      "prohibited_inferences": [
        "Do not invent unseen events or transitions"
      ],
      "fallback_behavior": "Do not block non-temporal indexing when temporal structure is not applicable or partly unavailable."
    },
    {
      "layer_number": 4,
      "layer_id": "PEOPLE_ROLES",
      "layer_name": "People & Roles",
      "description": "Represent visible people and their evidence-supported roles.",
      "purpose": "Make people and supported roles searchable without unauthorized identity inference.",
      "applicability_rules": [
        "Evaluate every visible person meeting detection thresholds"
      ],
      "expected_information": [
        "person instance",
        "visible-person count",
        "clinician",
        "doctor where supportable",
        "patient",
        "assistant/staff",
        "subject",
        "unknown role",
        "role confidence",
        "scene association"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Visible person evidence and role-specific cues or trusted context"
      ],
      "completeness_rules": [
        "COMPLETE when all qualifying visible persons were evaluated for role",
        "UNKNOWN role is a completed evaluation"
      ],
      "search_inclusion_rules": [
        "HIGH contribution for supported people and role facts"
      ],
      "search_critical_fields": [
        "person count",
        "role",
        "scene association"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "trusted metadata/context"
      ],
      "quality_rules": [
        "If a person is visible but role cues are insufficient, role is UNKNOWN"
      ],
      "prohibited_inferences": [
        "Do not identify a specific person without approved identity evidence",
        "Do not guess clinical roles from clothing or setting alone"
      ],
      "fallback_behavior": "Retain person presence/count while leaving unsupported roles UNKNOWN."
    },
    {
      "layer_number": 5,
      "layer_id": "PERSON_APPEARANCE",
      "layer_name": "Person Appearance",
      "description": "Describe visible search-useful presentation characteristics without inventing sensitive identity attributes.",
      "purpose": "Support appearance queries within privacy and sensitive-inference policy.",
      "applicability_rules": [
        "Applies when a person is visibly assessable",
        "Sensitive demographic inference follows project policy"
      ],
      "expected_information": [
        "apparent adult/child presentation where appropriate",
        "hair visibility",
        "hair length",
        "hair color",
        "hair density/pattern",
        "clothing",
        "PPE",
        "gloves",
        "mask",
        "eyewear",
        "posture",
        "reclining/seated/standing",
        "face visibility",
        "scalp visibility",
        "body orientation",
        "presentation state"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct visible evidence for each asserted characteristic"
      ],
      "completeness_rules": [
        "COMPLETE when applicable allowed appearance categories were evaluated",
        "UNKNOWN is valid completion"
      ],
      "search_inclusion_rules": [
        "Include only policy-allowed field-specific appearance facts"
      ],
      "search_critical_fields": [
        "clothing/PPE",
        "posture",
        "face/scalp visibility",
        "body orientation"
      ],
      "modality_dependencies": [
        "visual observations"
      ],
      "quality_rules": [
        "Occluded or blurry characteristics are UNKNOWN"
      ],
      "prohibited_inferences": [
        "Do not infer ethnicity from appearance",
        "Do not manufacture exact age",
        "Do not infer identity"
      ],
      "fallback_behavior": "Use UNKNOWN for unresolved visible characteristics and NOT_APPLICABLE when no person is present."
    },
    {
      "layer_number": 6,
      "layer_id": "ANATOMY",
      "layer_name": "Anatomy",
      "description": "Identify visible anatomical regions relevant to search.",
      "purpose": "Normalize supported anatomy for precise retrieval.",
      "applicability_rules": [
        "Applies when anatomy is visible or otherwise directly evidenced"
      ],
      "expected_information": [
        "canonical anatomy concept",
        "scalp",
        "frontal scalp",
        "frontal hairline",
        "cheek",
        "face",
        "lower face",
        "lips",
        "neck",
        "donor region",
        "recipient region",
        "scene association",
        "evidence",
        "confidence",
        "primary/secondary anatomy"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct reliable anatomy evidence with scene association"
      ],
      "completeness_rules": [
        "COMPLETE when applicable visible anatomy was evaluated across usable evidence",
        "UNKNOWN is valid when anatomy cannot be resolved"
      ],
      "search_inclusion_rules": [
        "VERY HIGH contribution from supported canonical anatomy"
      ],
      "search_critical_fields": [
        "canonical anatomy concept",
        "scene association"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure"
      ],
      "quality_rules": [
        "Blur, occlusion, or framing may require UNKNOWN"
      ],
      "prohibited_inferences": [
        "Do not infer anatomy solely from treatment name"
      ],
      "fallback_behavior": "Preserve broad supported regions and mark finer localization UNKNOWN."
    },
    {
      "layer_number": 7,
      "layer_id": "TREATMENT_PROCEDURE",
      "layer_name": "Treatment / Procedure",
      "description": "Identify treatment or procedure only when evidence supports the classification.",
      "purpose": "Provide high-value treatment retrieval without unsafe clinical guessing.",
      "applicability_rules": [
        "Evaluate whether treatment classification applies",
        "No treatment evidence may yield UNKNOWN or NOT_APPLICABLE according to evaluated context"
      ],
      "expected_information": [
        "canonical treatment concept",
        "procedure stage",
        "primary treatment",
        "related treatment evidence",
        "confidence",
        "scene association"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Treatment-specific visual, textual, transcript, or trusted contextual evidence"
      ],
      "completeness_rules": [
        "COMPLETE when treatment applicability was evaluated",
        "UNKNOWN treatment can coexist with COMPLETE evaluation"
      ],
      "search_inclusion_rules": [
        "VERY HIGH contribution only when OBSERVED and trusted"
      ],
      "search_critical_fields": [
        "canonical treatment concept",
        "procedure stage",
        "scene association"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "speech/audio",
        "OCR/visible text",
        "trusted metadata/context"
      ],
      "quality_rules": [
        "Ambiguous or low-quality procedure evidence is UNKNOWN"
      ],
      "prohibited_inferences": [
        "Anatomy plus action does not prove a specific treatment",
        "Neck plus injection does not prove Botox, filler, mesotherapy, or PRP"
      ],
      "fallback_behavior": "Keep supported anatomy/action facts while treatment remains UNKNOWN."
    },
    {
      "layer_number": 8,
      "layer_id": "ACTIONS_EVENTS",
      "layer_name": "Actions & Events",
      "description": "Identify visible or otherwise evidenced actions and events.",
      "purpose": "Represent what happens, who acts, and what is targeted.",
      "applicability_rules": [
        "Evaluate relevant visible or otherwise reliable actions/events"
      ],
      "expected_information": [
        "injecting",
        "drawing",
        "marking",
        "cleansing",
        "touching",
        "examining",
        "using device",
        "implanting grafts",
        "speaking",
        "posing",
        "recording video",
        "actor",
        "target",
        "scene/event",
        "confidence",
        "temporal interval"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct visual, temporal, audio, or trusted evidence"
      ],
      "completeness_rules": [
        "COMPLETE when relevant actions/events were evaluated",
        "UNKNOWN is permitted"
      ],
      "search_inclusion_rules": [
        "VERY HIGH contribution for trusted actions and events"
      ],
      "search_critical_fields": [
        "canonical action",
        "actor",
        "target",
        "temporal interval"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "speech/audio"
      ],
      "quality_rules": [
        "Do not over-specify ambiguous motion"
      ],
      "prohibited_inferences": [
        "Do not infer a specific action from setting alone",
        "Do not infer treatment from an action"
      ],
      "fallback_behavior": "Store only the broadest action supportable; otherwise UNKNOWN."
    },
    {
      "layer_number": 9,
      "layer_id": "RELATIONSHIPS",
      "layer_name": "Relationships",
      "description": "Represent evidence-supported relationships between entities.",
      "purpose": "Support relational natural-language queries.",
      "applicability_rules": [
        "Evaluate detected entities/actions for supported search-relevant relations"
      ],
      "expected_information": [
        "subject entity",
        "relationship type",
        "object entity",
        "clinician treats patient",
        "clinician touches cheek",
        "syringe applied to neck",
        "clinician works on scalp",
        "person uses device",
        "action targets anatomy",
        "scene/event context",
        "evidence",
        "confidence"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "All relation endpoints and the relation itself must be evidenced"
      ],
      "completeness_rules": [
        "COMPLETE when applicable detected entities/actions were evaluated for supported relations"
      ],
      "search_inclusion_rules": [
        "HIGH contribution for trusted relational facts"
      ],
      "search_critical_fields": [
        "subject",
        "relationship",
        "object",
        "scene/event"
      ],
      "modality_dependencies": [
        "structured semantic assertions",
        "scene/event structure",
        "visual observations"
      ],
      "quality_rules": [
        "Uncertain endpoints or linkage produce UNKNOWN rather than a guessed relation"
      ],
      "prohibited_inferences": [
        "Do not invent absence or presence of a relationship"
      ],
      "fallback_behavior": "Index supported independent entities/actions even when their relationship is UNKNOWN."
    },
    {
      "layer_number": 10,
      "layer_id": "CLINICAL_VISUAL_OBSERVATIONS",
      "layer_name": "Clinical Visual Observations",
      "description": "Store observable clinical facts without unsupported diagnosis.",
      "purpose": "Capture clinically useful visual facts while separating observation from diagnosis.",
      "applicability_rules": [
        "Applies to defined observable clinical categories when evidence exists"
      ],
      "expected_information": [
        "visible frontal thinning",
        "visible injection at neck",
        "treatment area prepared",
        "hairline markings visible",
        "scalp under active clinical attention",
        "eye protection visible",
        "clinical instrument visible",
        "observation code",
        "anatomical context",
        "scene",
        "evidence",
        "confidence"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct observable evidence linked to anatomy and scene where relevant"
      ],
      "completeness_rules": [
        "COMPLETE when applicable defined clinical-observation categories were evaluated"
      ],
      "search_inclusion_rules": [
        "HIGH contribution for grounded observation codes"
      ],
      "search_critical_fields": [
        "observation code",
        "anatomical context",
        "scene"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure"
      ],
      "quality_rules": [
        "Low quality limits observations to what remains directly supportable"
      ],
      "prohibited_inferences": [
        "No diagnosis unless explicitly supported by approved clinical evidence and policy"
      ],
      "fallback_behavior": "Use non-diagnostic broad observation or UNKNOWN."
    },
    {
      "layer_number": 11,
      "layer_id": "ENVIRONMENT",
      "layer_name": "Environment",
      "description": "Describe the physical setting.",
      "purpose": "Support setting and background discovery.",
      "applicability_rules": [
        "Evaluate visible environment for every usable visual asset"
      ],
      "expected_information": [
        "treatment room",
        "consultation room",
        "studio",
        "indoor room",
        "neutral background",
        "clinical environment",
        "outdoor environment",
        "background",
        "visible equipment context",
        "location class",
        "confidence"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct visual setting evidence or trusted location context"
      ],
      "completeness_rules": [
        "COMPLETE when applicable environmental categories were evaluated"
      ],
      "search_inclusion_rules": [
        "MEDIUM contribution for supported setting facts"
      ],
      "search_critical_fields": [
        "environment category",
        "background",
        "equipment context"
      ],
      "modality_dependencies": [
        "visual observations",
        "trusted metadata/context"
      ],
      "quality_rules": [
        "Tight framing may make detailed environment UNKNOWN"
      ],
      "prohibited_inferences": [
        "Do not infer a clinic or exact location from weak aesthetic cues"
      ],
      "fallback_behavior": "Use broad indoor/outdoor/unknown setting when finer classification is unsupported."
    },
    {
      "layer_number": 12,
      "layer_id": "CINEMATOGRAPHY",
      "layer_name": "Cinematography",
      "description": "Describe how the media was captured, including technical visual quality.",
      "purpose": "Support capture-style and quality-based discovery.",
      "applicability_rules": [
        "Applies to usable visual media"
      ],
      "expected_information": [
        "close-up",
        "extreme close-up",
        "medium",
        "wide",
        "front angle",
        "side angle",
        "handheld",
        "static",
        "moving camera",
        "orientation",
        "camera movement",
        "technical quality",
        "blur",
        "focus",
        "exposure"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct frame or sequence evidence"
      ],
      "completeness_rules": [
        "COMPLETE when applicable capture/quality categories were evaluated",
        "Observed blur does not make completeness PARTIAL"
      ],
      "search_inclusion_rules": [
        "MEDIUM/HIGH contribution when capture qualities are requested"
      ],
      "search_critical_fields": [
        "shot size",
        "angle",
        "motion",
        "orientation",
        "quality"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "technical/file metadata"
      ],
      "quality_rules": [
        "Low-quality imagery can still yield a COMPLETE cinematography evaluation"
      ],
      "prohibited_inferences": [
        "Do not translate technical quality into unsupported semantic content"
      ],
      "fallback_behavior": "Record supported capture facts even when semantic subjects remain unknown."
    },
    {
      "layer_number": 13,
      "layer_id": "COMPOSITION",
      "layer_name": "Composition",
      "description": "Describe spatial framing and visual arrangement.",
      "purpose": "Support framing, prominence, and layout queries.",
      "applicability_rules": [
        "Applies to usable visual media"
      ],
      "expected_information": [
        "primary subject",
        "central/off-center framing",
        "foreground/background",
        "subject prominence",
        "treatment area prominence",
        "single/multiple subject composition",
        "face/scalp/body prominence",
        "visual clutter"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Direct spatial/frame evidence"
      ],
      "completeness_rules": [
        "COMPLETE when applicable composition categories were evaluated"
      ],
      "search_inclusion_rules": [
        "MEDIUM contribution for supported composition facts"
      ],
      "search_critical_fields": [
        "primary subject",
        "framing",
        "prominence",
        "subject count"
      ],
      "modality_dependencies": [
        "visual observations"
      ],
      "quality_rules": [
        "Blur may affect semantic identification without preventing layout evaluation"
      ],
      "prohibited_inferences": [
        "Do not infer treatment or identity from prominence"
      ],
      "fallback_behavior": "Describe geometry and prominence without guessing subject semantics."
    },
    {
      "layer_number": 14,
      "layer_id": "SPEECH_TRANSCRIPT_AUDIO",
      "layer_name": "Speech / Transcript / Audio",
      "description": "Represent usable audio and speech evidence.",
      "purpose": "Capture trusted audio, speech, language, and transcript evidence without fabrication.",
      "applicability_rules": [
        "No audio track is NOT_APPLICABLE",
        "Audio without speech uses the ontology no-speech state",
        "Unintelligible speech makes transcript/language facts UNKNOWN"
      ],
      "expected_information": [
        "has_audio",
        "has_speech",
        "language",
        "transcript chunks",
        "speaker labels",
        "spoken summary",
        "audio event",
        "confidence",
        "timestamps"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Audio-track probe and accepted audio/speech processing output"
      ],
      "completeness_rules": [
        "COMPLETE when applicability was evaluated and all usable speech processed under audio policy",
        "Silent/no-audio files may be COMPLETE/NOT_APPLICABLE rather than PARTIAL"
      ],
      "search_inclusion_rules": [
        "Include only trusted/accepted transcript and audio evidence"
      ],
      "search_critical_fields": [
        "accepted transcript",
        "language",
        "audio event",
        "timestamps"
      ],
      "modality_dependencies": [
        "speech/audio",
        "technical/file metadata"
      ],
      "quality_rules": [
        "Unintelligible speech is UNKNOWN and never fabricated"
      ],
      "prohibited_inferences": [
        "Never invent transcript, language, speaker, or audio events"
      ],
      "fallback_behavior": "Continue all non-audio layers and indexing when audio is missing or unusable."
    },
    {
      "layer_number": 15,
      "layer_id": "OCR_VISIBLE_TEXT",
      "layer_name": "OCR / Visible Text",
      "description": "Represent visible readable text.",
      "purpose": "Capture trusted visible text with spatial and temporal provenance.",
      "applicability_rules": [
        "No visible text is NOT_APPLICABLE",
        "Visible but unreadable text is UNKNOWN",
        "Readable text is OBSERVED with transcription and confidence"
      ],
      "expected_information": [
        "detected text",
        "location/region",
        "scene/time",
        "confidence",
        "accepted/rejected search status"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Frame/region evidence and OCR confidence/acceptance decision"
      ],
      "completeness_rules": [
        "COMPLETE when applicable frames/scenes were evaluated under OCR policy",
        "Zero text is not extraction failure"
      ],
      "search_inclusion_rules": [
        "Include only accepted/trusted OCR"
      ],
      "search_critical_fields": [
        "accepted text",
        "location/region",
        "scene/time"
      ],
      "modality_dependencies": [
        "OCR/visible text",
        "visual observations",
        "scene/event structure"
      ],
      "quality_rules": [
        "Unreadable visible text is UNKNOWN"
      ],
      "prohibited_inferences": [
        "Never hallucinate text",
        "Unreadable OCR does not prove no text exists"
      ],
      "fallback_behavior": "Continue visual indexing when OCR is absent, unreadable, or rejected."
    },
    {
      "layer_number": 16,
      "layer_id": "MARKETING_CONTENT_USAGE",
      "layer_name": "Marketing & Content Usage",
      "description": "Describe content characteristics useful for discovery and distribution planning without representing consent.",
      "purpose": "Support content-planning queries while keeping governance separate.",
      "applicability_rules": [
        "Evaluate defined marketing-content categories when supportable"
      ],
      "expected_information": [
        "testimonial potential",
        "procedure footage",
        "portrait content",
        "before/after suitability",
        "educational content",
        "promotional candidate",
        "social-media suitability",
        "orientation suitability",
        "quality limitations"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "FALSE",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Grounded content, orientation, and quality evidence"
      ],
      "completeness_rules": [
        "COMPLETE when defined marketing-content categories were evaluated"
      ],
      "search_inclusion_rules": [
        "Include only when relevant to the query"
      ],
      "search_critical_fields": [
        "content type",
        "potential use",
        "orientation suitability",
        "quality limitations"
      ],
      "modality_dependencies": [
        "visual observations",
        "scene/event structure",
        "semantic narrative",
        "technical/file metadata"
      ],
      "quality_rules": [
        "Record limitations explicitly"
      ],
      "prohibited_inferences": [
        "Marketing suitability is not patient consent",
        "Do not infer ACL, rights, or consent"
      ],
      "fallback_behavior": "Return UNKNOWN suitability where content evidence is insufficient; governance remains external."
    },
    {
      "layer_number": 17,
      "layer_id": "SEMANTIC_NARRATIVE",
      "layer_name": "Semantic Narrative",
      "description": "Create evidence-grounded human-readable summaries of the asset and important scenes/events.",
      "purpose": "Provide readable synthesis without creating new facts.",
      "applicability_rules": [
        "Generate required narrative forms from available trusted evidence"
      ],
      "expected_information": [
        "short description",
        "detailed/master description",
        "scene narrative",
        "narrative claims",
        "evidence linkage",
        "confidence/uncertainty",
        "search eligibility status"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Every factual narrative claim links to trusted structured evidence"
      ],
      "completeness_rules": [
        "COMPLETE when required narratives were generated and every factual claim is grounded"
      ],
      "search_inclusion_rules": [
        "Include only narratives eligible under the locked grounded-narrative policy"
      ],
      "search_critical_fields": [
        "short description",
        "master description",
        "grounded scene narrative"
      ],
      "modality_dependencies": [
        "structured semantic assertions",
        "scene/event structure",
        "trusted metadata/context"
      ],
      "quality_rules": [
        "Narrative must expose material uncertainty"
      ],
      "prohibited_inferences": [
        "Narrative may not create facts unsupported by structured semantic evidence"
      ],
      "fallback_behavior": "Produce a narrower narrative from reliable evidence rather than filling gaps."
    },
    {
      "layer_number": 18,
      "layer_id": "SEARCH_EMBEDDINGS",
      "layer_name": "Search & Embeddings",
      "description": "Create reusable search representations from trusted semantic evidence.",
      "purpose": "Provide the primary retrieval representation with complete evidence lineage.",
      "applicability_rules": [
        "Build from all reliable available evidence",
        "No single modality is mandatory"
      ],
      "expected_information": [
        "canonical search document",
        "normalized search text",
        "positive concepts",
        "supported negative concepts",
        "search-document fingerprint",
        "text embedding",
        "visual embedding where applicable",
        "scene embedding where applicable",
        "embedding provider/model/version",
        "dimension",
        "evidence lineage"
      ],
      "allowed_semantic_states": [
        "OBSERVED",
        "UNKNOWN",
        "NOT_APPLICABLE"
      ],
      "evidence_requirements": [
        "Every included representation traces to trusted evidence and the current locked semantic version"
      ],
      "completeness_rules": [
        "COMPLETE when all required representations applicable to the asset were built",
        "An unavailable modality alone does not make the layer PARTIAL"
      ],
      "search_inclusion_rules": [
        "PRIMARY RETRIEVAL REPRESENTATION",
        "Combine relevant available evidence; do not privilege a fixed primary field"
      ],
      "search_critical_fields": [
        "canonical search document",
        "normalized search text",
        "concepts",
        "embeddings",
        "provider/model/version",
        "evidence lineage"
      ],
      "modality_dependencies": [
        "all reliable available modalities"
      ],
      "quality_rules": [
        "Exclude rejected, hallucinated, or ungrounded material"
      ],
      "prohibited_inferences": [
        "Do not require audio, OCR, treatment, identity, or any single modality",
        "Do not include unsupported negative concepts"
      ],
      "fallback_behavior": "Build the applicable subset of search representations from trusted available evidence."
    }
  ],
  "fingerprint_contract": {
    "algorithm": "SHA-256",
    "canonicalization": "UTF-8 JSON; lexicographically sorted object keys; compact separators comma and colon; omit only top-level spec_fingerprint"
  },
  "spec_fingerprint": "6da50e2153f6fcb6c9ef27c308ad44d0d2024e702e3faad47586b0068ba64fd7"
}
```
