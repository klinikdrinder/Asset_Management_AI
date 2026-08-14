import{fetchDriveMedia,mediaErrorResponse,mediaHeaders}from"../../../../media-service";
export const dynamic="force-dynamic";
export async function GET(request:Request,{params}:{params:Promise<{sourceFileId:string}>}){
 try{const media=await fetchDriveMedia((await params).sourceFileId,request.headers.get("range"),request.signal,true);return new Response(media.upstream.body,{status:media.upstream.status,headers:mediaHeaders(media.record,media.upstream,"attachment")})}catch(error){return mediaErrorResponse(error,{operation:"download"})}
}
