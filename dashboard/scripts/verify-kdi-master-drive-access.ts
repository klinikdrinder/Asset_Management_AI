// Phase 9 read-only diagnostic: proves the server-side Google service
// account can authenticate, reach the configured KDI Master Shared Drive,
// and read a known verified destination file's metadata and bytes - without
// any manually copied user token, and without modifying any Drive file.
//
// Usage (from dashboard/):
//   npm run drive:verify
//   npm run drive:verify -- <known-destination-google-file-id>
// If no file id is given, one VERIFIED asset_destinations row is looked up
// read-only from Supabase.
import "server-only";
import nextEnv from "@next/env";
nextEnv.loadEnvConfig(process.cwd());

function assert(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}

async function main() {
  const { getDriveJwtClient, getDriveAccessToken, resolveKdiMasterDriveId, GoogleServiceAccountError } = await import("../app/lib/google/service-account");
  const { getDriveAbout, getSharedDriveMetadata, getDriveFileMetadata, downloadDriveFile, DriveApiError } = await import("../app/lib/google/drive-client");

  // Step 1: credentials resolve and the service account can authenticate.
  let clientEmail = "unknown";
  try {
    const client = getDriveJwtClient();
    clientEmail = client.email ?? "unknown";
    await getDriveAccessToken();
    console.log(`credential_source=${process.env.GOOGLE_DRIVE_SERVICE_ACCOUNT_EMAIL ? "env_key_pair" : process.env.GOOGLE_DRIVE_SERVICE_ACCOUNT_CREDENTIALS_JSON ? "inline_json" : "credentials_file"}`);
    console.log("service_account_authenticated=true");
    console.log(`service_account_email=${clientEmail}`);
  } catch (error) {
    if (error instanceof GoogleServiceAccountError) throw new Error(`service_account_authentication_failed:${error.code}`);
    throw error;
  }
  console.log("manual_user_token_required=false");

  // Step 2: the token is genuinely a working Drive OAuth token (no Shared
  // Drive access implied yet - /about only requires the drive.readonly scope).
  const about = await getDriveAbout();
  console.log(`drive_api_reachable=true authenticated_as=${about.user?.emailAddress ?? "unknown"}`);

  // Step 3: the service account can access the configured KDI_MASTER_DRIVE_ID.
  // This id may be a genuine Shared Drive id (drives.get) or a regular
  // folder id living inside a Shared Drive or a personal Drive
  // (files.get) - the repository's own Step 10 records never captured
  // which kind was actually used, so both are tried read-only here and the
  // real answer is reported rather than assumed.
  const driveId = resolveKdiMasterDriveId();
  try {
    const sharedDrive = await getSharedDriveMetadata(driveId);
    console.log(`kdi_master_drive_accessible=true resource_type=shared_drive drive_id=${sharedDrive.id} drive_name=${sharedDrive.name}`);
  } catch (sharedDriveError) {
    if (!(sharedDriveError instanceof DriveApiError) || sharedDriveError.code !== "drive_not_found") {
      throw sharedDriveError instanceof DriveApiError ? new Error(`kdi_master_drive_access_failed:${sharedDriveError.code}(http_${sharedDriveError.status})`) : sharedDriveError;
    }
    try {
      const folder = await getDriveFileMetadata(driveId, "id,name,mimeType,driveId", undefined);
      console.log(`kdi_master_drive_accessible=true resource_type=folder folder_id=${folder.id} folder_name=${folder.name} inside_shared_drive=${Boolean(folder.driveId)}`);
    } catch (folderError) {
      if (folderError instanceof DriveApiError) throw new Error(`kdi_master_drive_access_failed:${folderError.code}(http_${folderError.status})`);
      throw folderError;
    }
  }

  // Step 4: resolve a known verified destination file id.
  const cliFileId = process.argv[2]?.trim();
  let knownFileId = cliFileId;
  if (!knownFileId) {
    const { createServiceClient } = await import("../app/lib/supabase/service");
    const { data, error } = await createServiceClient()
      .from("asset_destinations")
      .select("destination_google_file_id")
      .eq("upload_status", "VERIFIED")
      .not("destination_google_file_id", "is", null)
      .limit(1)
      .maybeSingle();
    assert(!error && data?.destination_google_file_id, "no_verified_destination_file_available_for_diagnostic");
    knownFileId = String(data!.destination_google_file_id);
  }
  console.log(`known_destination_file_selected=true file_id_present=true`);

  // Step 5: metadata can be retrieved (read-only, supportsAllDrives).
  let metadata;
  try {
    metadata = await getDriveFileMetadata(knownFileId, "id,name,mimeType,size,modifiedTime,driveId", undefined);
  } catch (error) {
    if (error instanceof DriveApiError) throw new Error(`known_file_metadata_failed:${error.code}(http_${error.status})`);
    throw error;
  }
  console.log(`known_file_metadata_retrieved=true mime_type=${metadata.mimeType} file_shared_drive_id=${metadata.driveId ?? "none"}`);

  // Step 6: media bytes can be retrieved (a tiny range only - read-only).
  try {
    const response = await downloadDriveFile(knownFileId, { range: "bytes=0-63" });
    const bytes = new Uint8Array(await response.arrayBuffer());
    assert(bytes.length > 0, "known_file_bytes_empty");
    console.log(`known_file_bytes_retrieved=true bytes_read=${bytes.length} status=${response.status}`);
  } catch (error) {
    if (error instanceof DriveApiError) throw new Error(`known_file_bytes_failed:${error.code}(http_${error.status})`);
    throw error;
  }

  console.log("KDI_MASTER_DRIVE_ACCESS_VERIFIED");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : "kdi_master_drive_verification_failed");
  process.exitCode = 1;
});
