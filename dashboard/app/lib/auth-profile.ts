import "server-only";

import { createServiceClient } from "./supabase/service";

export type DatabaseProfile = {
  user_id: string; email: string; role: "STAFF" | "ADMIN"; is_active: boolean;
  can_view_clinical: boolean; can_download: boolean; firebase_uid: string | null;
};

export async function profileForFirebaseUid(uid: string): Promise<DatabaseProfile | null> {
  const { data, error } = await createServiceClient().from("app_users")
    .select("user_id,email,role,is_active,can_view_clinical,can_download,firebase_uid")
    .eq("firebase_uid", uid).maybeSingle();
  if (error || !data) return null;
  return data as DatabaseProfile;
}
