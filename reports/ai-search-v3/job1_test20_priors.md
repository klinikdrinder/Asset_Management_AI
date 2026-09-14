# Job 1 test-20 — metadata-only priors (written before the run)

Basis: filename, source_folder, source_path, file size. NOT the model. These are
the checks to hold the results against.

## Videos — `Nushad Raw Video` (raw clinic footage; flat folder, no path)
Consecutive IMG numbers likely = same procedure session; large size = longer clip.

1. a3f48526 IMG_1147.MP4 (88 MB) — longest clip; expect a full procedure in a treatment/operating room: clinician + patient, scalp or face anatomy, a procedure action (implanting/extracting/injecting/using device). Specific procedure unknown from metadata — predict FUE hair transplant or an injectable.
2. 8100b032 IMG_4821.MP4 (60 MB) — part of the IMG_482x/483x cluster (with 4830/4831/4832/4854); expect the SAME procedure type across those five. Treatment room, clinician+patient, scalp/face.
3. 22696246 IMG_4854.MP4 (52 MB) — same 48xx session cluster; same procedure type expected as #2/#4/#6/#9.
4. 675d4482 IMG_4832.MP4 (46 MB) — 48xx cluster; same procedure type.
5. fa3ede68 IMG_0971.MP4 (41 MB) — IMG_09xx (with 0476); procedure footage; scalp/face, clinician+patient.
6. e3269ad6 IMG_4830.MP4 (40 MB) — 48xx cluster; same procedure type.
7. 99b42b59 IMG_6383.MP4 (38 MB) — standalone; procedure footage, treatment room.
8. f9d1e5ed IMG_0476.MP4 (37 MB) — 04xx; procedure footage, scalp/face.
9. aee119a2 IMG_4831.MP4 (36 MB) — 48xx cluster; same procedure type.
10. 46feb6c5 IMG_3481.MP4 (31 MB) — standalone; procedure footage.

Aggregate prior for videos: nearly all should yield ENVIRONMENT=treatment/operating room, PEOPLE_ROLES doctor+patient (± staff), RELATIONSHIPS doctor-treating/injecting-patient, ANATOMY scalp/face regions, ACTIONS a procedure verb, TREATMENT either a specific FUE/injectable code (if clearly shown) or UNDETERMINED. If most TREATMENT come back UNDETERMINED, that is the 0.7 floor biting — the number to watch.

## Images — `ALL PATIENT REVIEW` (clinical documentation)
3. LIM TJUN CHERN / FUE DAY-25.03.10 (procedure day):
- 07ad553b DSC03385.JPG, 07afa0fe DSC03398.JPG, 07f04fb6 DSC03417.JPG — hair-transplant day photos: shaved donor/recipient scalp, frontal scalp/hairline, extraction or graft sites, likely redness. Expect ANATOMY scalp/frontal_scalp/recipient_region/donor_region; CLINICAL extraction_sites_visible / recipient_region_visible / redness / during- or pre-transplant; TREATMENT hair transplant (FUE) if graft work is visible, else UNDETERMINED. Likely no live "action" (still photo) → ACTIONS UNKNOWN/empty.
2. DR MOHD MUZAFFAR / DAY 1 (post-op day 1):
- 0b46b4fd 26.01 (2).jpeg, 24ce6830 26.01 (7).jpeg, 2e5bec8d 26.01 (1).jpeg — day-1 post-transplant scalp: recipient region with fresh grafts, crusting/redness, frontal hairline. Expect ANATOMY frontal_scalp/recipient_region; CLINICAL graft_sites_visible / recipient_region_visible / redness / post-transplant; TREATMENT UNDETERMINED or hair transplant.
3. SYED AHMAD AL-HADDAD / 1 MONTH (post-op review):
- 21c46d8b DSC01738.JPG, 271e8558 DSC01737.JPG, 4628b0be DSC01736.JPG — one-month review: healing scalp, early regrowth, recipient region. Less active treatment; expect ANATOMY scalp/frontal_scalp; CLINICAL hair_density_visual / recipient_region_visible / post-transplant; TREATMENT UNDETERMINED.
1. AMINATH USWA IBRAHIM / 2025.08.06:
- 002b4ba0 DSC05871.JPG — review photo, stage unclear from path; expect a face/scalp portrait with some clinical observation (thinning/hairline) or a general clinical documentation image; TREATMENT likely UNDETERMINED.

Aggregate prior for images: strong ANATOMY + CLINICAL_VISUAL_OBSERVATIONS coverage, ENVIRONMENT often UNDETERMINED or clinic, ACTIONS mostly empty (stills), TREATMENT mostly UNDETERMINED unless graft/extraction work is unambiguous. Post-op review images (1 MONTH) should be lighter on treatment signals than procedure-day (FUE DAY / DAY 1) images.
