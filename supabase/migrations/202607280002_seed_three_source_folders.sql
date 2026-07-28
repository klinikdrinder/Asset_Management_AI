begin;

insert into public.source_folders (
  source_name,
  account_name,
  folder_url,
  google_folder_id,
  active,
  access_status,
  permission_role,
  notes
)
values
  (
    'Nushad Raw Video',
    'kdimktgsubang@gmail.com',
    'https://drive.google.com/drive/folders/1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI?usp=drive_link',
    '1J7rUY-n4oVFqwY07jXOwwu_wFo8jeCsI',
    true,
    'PENDING',
    'UNKNOWN',
    'Initial approved Google Drive source folder.'
  ),
  (
    'ALL PATIENT REVIEW',
    'kdisubang@gmail.com',
    'https://drive.google.com/drive/folders/1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v',
    '1kYX3KIEFkerRMrTvZk2zPpVaFQoCLE4v',
    true,
    'PENDING',
    'UNKNOWN',
    'Initial approved Google Drive source folder.'
  ),
  (
    'Photo/Video for Marketing (Consented by patient)',
    'kdisubang@gmail.com',
    'https://drive.google.com/drive/folders/1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt',
    '1TkV6WEH5ymgqZmU7WgYFwYeZUxGYkEUt',
    true,
    'PENDING',
    'UNKNOWN',
    'Patient media source. Consent status must still be verified at asset level.'
  )

on conflict (google_folder_id)
do nothing;

commit;
