# Job 6 permission verification

External-AI gate: PASS (10/10 selected TRUE; restricted DSC00365.JPG, IMG_0588.MP4, IMG_1253.MP4 FALSE; held DSC03759.JPG FALSE). Restricted/backup analysis runs: 0.

RLS remains enabled. Direct anon/authenticated SELECT and TRUNCATE privileges are false for scenes, keyframes, transcripts, OCR, clinical observations, structured child tables, search documents, and vector tables. PUBLIC/anon/authenticated execute on the private external-AI function is false. The least-privilege Job 6 migration grants only service-role worker access to transcript rows/sequence and is recorded in migration history.

Live unauthenticated downloads for a selected UUID, restricted UUID, and constructed UUID returned HTTP 401 without storage/source/private-data leakage. Health/login/library returned 200/200/307. View/download separation and authorized-download behavior remain covered by the unchanged Job 5.2 implementation and regression suite.
