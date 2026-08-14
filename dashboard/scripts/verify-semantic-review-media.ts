// Read-only runtime verification for semantic-review media delivery.
import "server-only";
import nextEnv from "@next/env";
import { readFile } from "node:fs/promises";
import path from "node:path";
nextEnv.loadEnvConfig(process.cwd());

async function main(){
  const { createServiceClient }=await import("../app/lib/supabase/service");
  const { resolveFromAssetRow }=await import("../app/lib/media/resolve-location");
  const { getDriveJwtClient }=await import("../app/lib/google/service-account");
  const { getDriveFileMetadata,downloadDriveFile,fetchDriveThumbnailLinkBytes }=await import("../app/lib/google/drive-client");
  const manifest=JSON.parse(await readFile(path.resolve(process.cwd(),"..","data","semantic_manual_benchmark_20.json"),"utf8")) as {assets:{asset_id:string;media_type:"image"|"video"}[]};
  const selected=[manifest.assets.find(row=>row.media_type==="image"),manifest.assets.find(row=>row.media_type==="video")];
  if(selected.some(row=>!row))throw new Error("semantic_review_fixture_missing_media_type");
  getDriveJwtClient();
  console.log("credential=AVAILABLE auth_method=SERVICE_ACCOUNT_SERVER_SIDE");
  for(const asset of selected){
    const {data,error}=await createServiceClient().from("assets").select("id,file_name,mime_type,file_extension,size_bytes,upload_status,asset_destinations(id,destination_google_file_id,destination_filename,upload_status,verified_at,upload_completed_at)").eq("id",asset!.asset_id).eq("asset_destinations.upload_status","VERIFIED").maybeSingle();
    if(error||!data)throw new Error(`canonical_destination_lookup_failed:${asset!.media_type}`);
    const {location,reason}=resolveFromAssetRow(data);
    if(!location||reason!=="destination"||location.source!=="destination")throw new Error(`canonical_destination_invalid:${asset!.media_type}`);
    const metadata=await getDriveFileMetadata(location.driveFileId,"id,mimeType,size,thumbnailLink,driveId");
    if(asset!.media_type==="image"){
      if(!metadata.thumbnailLink)throw new Error("image_thumbnail_unavailable");
      const thumbnail=await fetchDriveThumbnailLinkBytes(metadata.thumbnailLink);const bytes=new Uint8Array(await thumbnail.arrayBuffer());
      if(!bytes.length||!thumbnail.headers.get("content-type")?.startsWith("image/"))throw new Error("image_thumbnail_invalid");
      console.log(`image_destination=VERIFIED metadata=OK thumbnail=OK bytes=${bytes.length}`);
    }else{
      const response=await downloadDriveFile(location.driveFileId,{range:"bytes=0-1023"});const bytes=new Uint8Array(await response.arrayBuffer()),contentRange=response.headers.get("content-range");
      if(response.status!==206||!contentRange?.startsWith("bytes 0-1023/")||bytes.length!==1024)throw new Error("video_range_invalid");
      console.log(`video_destination=VERIFIED metadata=OK range_status=${response.status} content_range=VALID bytes=${bytes.length}`);
    }
  }
  console.log("oauth_user=false local_fallback=false source_fallback=false browser_credentials=false");
  console.log("KDI_SEMANTIC_REVIEW_MEDIA_RUNTIME_VERIFIED");
}
main().catch(error=>{console.error(error instanceof Error?error.message:"semantic_review_media_verification_failed");process.exitCode=1});
