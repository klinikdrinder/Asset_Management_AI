"""Builds the one canonical search vocabulary registry.

The registry is the single natural-language to canonical-concept mapping for the whole search
pipeline. It is a strict superset of the aliases previously embedded in the parser config, plus
wording for concepts that are already OBSERVED in the certified index but had no query-side route.

Query-side only: this never alters semantic truth. A named clinical procedure stays reachable only
from explicit procedure wording; generic gloves, instrument, scalp or contact wording never resolves
to a named procedure.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SRC = R / 'config/semantic-search/kdi_query_parser_v1_4.json'
OUT = R / 'config/semantic-search/kdi_search_vocabulary_v1.json'

ADD = {
    'ROLE': {'SUBJECT': ['subject', 'person in the video', 'filmed subject']},
    'OBSERVATION': {
        'BROAD_ENVIRONMENT_VISIBLE': ['broad environment', 'wider environment',
                                      'indoor or outdoor environment', 'surrounding environment'],
        'SCALP_UNDER_ACTIVE_CLINICAL_ATTENTION': ['scalp under clinical attention', 'scalp being worked on'],
        'FACE_UNDER_ACTIVE_CLINICAL_ATTENTION': ['face under clinical attention', 'face being worked on'],
        'PREPARED_FRONTAL_SCALP': ['prepared frontal scalp'],
        'SKIN_CLEANSING_IN_PROGRESS': ['skin cleansing in progress', 'skin being cleansed'],
        'VISIBLE_FRONTAL_HAIR_THINNING': ['frontal hair thinning', 'hair thinning', 'thinning hair',
                                          'reduced hair density'],
        'VISIBLE_INJECTION_AT_LOWER_FACE': ['injection at the lower face', 'lower face injection'],
        'VISIBLE_INJECTION_AT_NECK': ['injection at the neck', 'neck injection'],
        'VISIBLE_RECIPIENT_AREA_PROCEDURE': ['recipient area procedure'],
    },
    'ANATOMY': {'FACE': ['the face', 'human face'], 'SCALP': ['the scalp'],
                'CHEEK': ['cheek', 'the cheek'], 'LIPS': ['lips', 'the lips'],
                'LOWER_FACE': ['lower face'], 'NECK': ['neck', 'the neck']},
    'ACTION': {
        'TOUCHING': ['touching', 'making contact'],
        'LOOKING_AT_CAMERA': ['looking at camera'],
        'POSING_FOR_CAMERA': ['posing for the camera', 'posing for camera'],
        'RECORDING_VIDEO': ['recording video', 'filming themselves'],
        'USING_DEVICE': ['using a device', 'operating a device', 'handling a device'],
        'CLEANSING': ['cleansing', 'cleaning the skin', 'wiping the skin'],
        'HOLDING_SYRINGE': ['holding a syringe', 'syringe in hand'],
        'PHYSICAL_CONTACT_HOLDING_OR_MANIPULATION_VISIBLE': ['physical contact', 'contact or manipulation',
                                                            'holding or manipulation'],
    },
    'ENVIRONMENT': {'OPERATING_ROOM': ['operating room', 'operating theatre', 'operating theater']},
    'CINEMATOGRAPHY': {
        'CLOSEUP': ['close-up', 'close up', 'closeup', 'close-up shot', 'close up shot', 'tight shot'],
        'EXTREME_CLOSEUP': ['extreme close-up', 'extreme close up', 'extreme closeup', 'macro shot'],
        'MEDIUM_CLOSEUP': ['medium close-up', 'medium close up', 'medium closeup'],
        'MEDIUM': ['medium shot'],
        'HANDHELD': ['handheld camera', 'hand-held camera', 'handheld shot', 'shaky camera', 'moving camera'],
        'STATIC': ['static camera', 'static shot', 'fixed camera', 'tripod shot'],
        'VERTICAL': ['vertical video', 'vertical framing', 'portrait orientation'],
        'LANDSCAPE': ['landscape orientation', 'horizontal video', 'landscape framing'],
        'FRONT_ANGLE': ['front angle', 'frontal angle', 'front-on view'],
        'SELF_RECORDED': ['self recorded', 'self-recorded', 'selfie video'],
    },
    'COMPOSITION': {
        'FACE_PROMINENT': ['face prominent', 'prominent face', 'face fills the frame'],
        'PATIENT_FACE_PROMINENT': ['patient face prominent'],
        'PATIENT_HEAD_PROMINENT': ['patient head prominent'],
        'PATIENT_HEAD_AND_CLINICIAN_DOMINANT': ['patient head and clinician dominant'],
        'SINGLE_CENTRAL_SUBJECT': ['single central subject', 'one central subject', 'centred subject',
                                   'centered subject'],
        'SINGLE_CENTRAL_FACE': ['single central face', 'one central face'],
        'CLINICIAN_HANDS_IN_FOREGROUND': ['clinician hands in the foreground', 'hands in the foreground'],
        'MULTIPLE_CLINICAL_HANDS_VISIBLE': ['multiple clinical hands', 'several hands visible'],
        'CLINICIAN_AND_DEVICE_IN_FRAME': ['clinician and device in frame'],
        'DARK_NEUTRAL_BACKGROUND': ['dark neutral background', 'dark background'],
        'PLAIN_LIGHT_BACKGROUND': ['plain light background', 'plain background', 'light background'],
        'PATIENT_AND_CLINICIAN_VISIBLE': ['patient and clinician visible', 'both patient and clinician'],
        'TOOL_VISIBLE_NEAR_TREATMENT_AREA': ['tool near the treatment area'],
        'SWAB_IN_FOREGROUND': ['swab in the foreground'],
        'FRONTAL_SCALP_CENTRAL': ['frontal scalp central'],
        'FACE_AND_FRONTAL_SCALP_PROMINENT': ['face and frontal scalp prominent'],
        'CHEEK_AND_LOWER_FACE_DOMINANT': ['cheek and lower face dominant'],
        'NECK_TREATMENT_AREA_DOMINANT': ['neck treatment area dominant'],
        'TREATMENT_AREA_PARTIALLY_VISIBLE': ['treatment area partially visible'],
    },
    'APPEARANCE': {
        'ADULT_PRESENTATION': ['adult presentation', 'adult subject', 'an adult'],
        'CLINICIAN_GLOVED': ['gloved clinician', 'clinician wearing gloves'],
        'CLINICIAN_MASKED': ['masked clinician', 'clinician wearing a mask'],
        'CLINICAL_PPE_VISIBLE': ['clinical ppe', 'protective equipment visible', 'ppe visible'],
        'EYE_PROTECTION_VISIBLE': ['eye protection', 'protective eyewear', 'eye pads'],
        'PATIENT_RECLINING': ['reclining patient', 'patient lying back', 'patient reclined'],
        'FRONT_FACING': ['front facing', 'facing the camera'],
        'SEATED_OR_STANDING_UNKNOWN': ['seated or standing unknown'],
        'SHORT_DARK_HAIR': ['short dark hair'],
        'DARK_CLOTHING': ['dark clothing'],
        'DARK_HEAD_COVERING': ['dark head covering', 'head covering'],
        'WHITE_COLLARED_SHIRT': ['white collared shirt', 'collared shirt'],
        'SCALP_PREPARED': ['prepared scalp', 'scalp prepared'],
    },
    'RELATIONSHIP': {
        'CLINICIAN_TREATS_PATIENT': ['clinician treating a patient', 'doctor treating a patient',
                                     'clinician treats patient'],
        'CLINICIAN_WORKS_ON_ANATOMY': ['clinician working on', 'clinician works on'],
        'PATIENT_POSITIONED_IN_TREATMENT_CHAIR': ['patient in the treatment chair',
                                                  'patient positioned in a chair', 'treatment chair'],
        'PERSON_LOOKS_AT_CAMERA': ['person looking at the camera', 'looking at the camera'],
    },
    'CONTENT_USAGE': {
        'CLINICAL_REFERENCE': ['clinical reference', 'clinical reference material'],
        'PORTRAIT_CONTENT': ['portrait content', 'portrait photo'],
        'PROCEDURE_CONTENT': ['procedure content'],
        'PROCEDURE_PREPARATION_CONTENT': ['procedure preparation content', 'preparation content'],
        'EDUCATIONAL_CANDIDATE': ['educational content'],
        'PROMOTIONAL_CANDIDATE': ['promotional content', 'marketing content'],
        'CLINICAL_DOCUMENTATION_CANDIDATE': ['clinical documentation'],
        'SELF_RECORDED_CONTENT': ['self recorded content'],
        'HAIR_TRANSPLANT_PROCEDURE_CONTENT': ['hair transplant procedure content'],
    },
    'VISIBLE_TEXT': {'VISIBLE_TEXT': ['visible text', 'text on screen', 'on-screen text', 'on screen text',
                                      'readable text', 'readable on-screen text', 'writing visible',
                                      'words shown', 'text overlay']},
    'AUDIO': {'AUDIO_STREAM_PRESENT': ['audio track', 'an audio track', 'has audio', 'with sound',
                                       'audio present']},
}


def main():
    base = json.loads(SRC.read_text(encoding='utf-8'))['semantic_aliases']
    merged = collections.OrderedDict()
    for cat, codes in base.items():
        merged[cat] = {code: list(terms) for code, terms in codes.items()}
    for cat, codes in ADD.items():
        target = merged.setdefault(cat, {})
        for code, terms in codes.items():
            current = target.setdefault(code, [])
            seen = {t.lower() for t in current}
            for t in terms:
                if t.lower() not in seen:
                    current.append(t)
                    seen.add(t.lower())
    # The registry must never lose a mapping the parser already had.
    for cat, codes in base.items():
        assert set(codes) <= set(merged[cat]), cat
        for code, terms in codes.items():
            assert set(terms) <= set(merged[cat][code]), (cat, code)

    payload = {
        'search_vocabulary_version': 'kdi_search_vocabulary_v1',
        'supersedes': ['config/semantic-search/kdi_query_parser_v1_4.json#semantic_aliases'],
        'policy': ('One canonical natural-language to canonical-concept mapping for the entire search '
                   'pipeline. Additions are query-side only and never alter semantic truth. A named '
                   'clinical procedure is reachable only from explicit procedure wording; generic '
                   'gloves, instrument, scalp or contact wording never resolves to a named procedure.'),
        'categories': merged,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    base_codes = {c for cat in base.values() for c in cat}
    all_codes = {c for cat in merged.values() for c in cat}
    print(json.dumps({'categories': len(merged), 'concepts': len(all_codes),
                      'previously': len(base_codes), 'added': len(all_codes - base_codes)}))


if __name__ == '__main__':
    main()
