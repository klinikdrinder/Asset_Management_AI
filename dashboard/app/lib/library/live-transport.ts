import"server-only";
import{requireActiveAppUser}from"../../auth";
import{getSupabasePublicConfig}from"../supabase/config";
import{getFirebaseSupabaseToken}from"./authenticated-token";
export class LiveLibraryUnavailable extends Error{readonly code="live_library_unavailable"}
export async function liveRest(path:string,init:RequestInit={}){await requireActiveAppUser();const token=await getFirebaseSupabaseToken();if(!token)throw new LiveLibraryUnavailable("Authenticated library token unavailable");const{url,key}=getSupabasePublicConfig();let response:Response;try{response=await fetch(`${url}/rest/v1/${path}`,{...init,headers:{apikey:key,Authorization:`Bearer ${token}`,...init.headers},cache:"no-store"})}catch{throw new LiveLibraryUnavailable("Live library request unavailable")}if(!response.ok)throw new LiveLibraryUnavailable("Live library request rejected");return response}
