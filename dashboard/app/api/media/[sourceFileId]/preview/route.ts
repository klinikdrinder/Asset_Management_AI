import{fetchDriveMedia,mediaErrorResponse,mediaHeaders}from"../../../../media-service";
export const dynamic="force-dynamic";
export async function GET(request:Request,{params}:{params:Promise<{sourceFileId:string}>}){
 try{const id=(await params).sourceFileId,media=await fetchDriveMedia(id,request.headers.get("range"),request.signal),ext=media.record.extension.toLowerCase();if(ext==="pptx")return new Response("The presentation preview could not be generated. You may download the original file.",{status:503,headers:{"Cache-Control":"private, no-store"}});return new Response(media.upstream.body,{status:media.upstream.status,headers:mediaHeaders(media.record,media.upstream,"inline")})}catch(error){return mediaErrorResponse(error,{operation:"preview"})}
}
