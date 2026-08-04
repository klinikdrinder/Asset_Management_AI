import"server-only";
import{cookies}from"next/headers";
export const FIREBASE_SUPABASE_TOKEN_COOKIE="kdi_firebase_supabase_token";
export async function getFirebaseSupabaseToken(){return(await cookies()).get(FIREBASE_SUPABASE_TOKEN_COOKIE)?.value??null}
