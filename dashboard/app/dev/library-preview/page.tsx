import { notFound } from "next/navigation";
import { isLocalLibraryPreviewActive } from "../../lib/library/local-preview";
import { getDevMediaAssets } from "../../lib/media/dev-repository";
import { createServiceClient } from "../../lib/supabase/service";
import { LocalPreviewClient, type PreviewUser } from "./local-preview-client";

export const dynamic = "force-dynamic";

async function previewUsers(): Promise<PreviewUser[]> {
  const { data, error } = await createServiceClient()
    .from("app_users")
    .select("email,management_role,is_active,invited_at")
    .order("email", { ascending: true })
    .limit(100);
  if (error) return [];
  return (data ?? []).map((user) => ({
    email: String(user.email ?? ""),
    role: String(user.management_role ?? "staff"),
    status: user.is_active ? "Active" : user.invited_at ? "Invitation Sent" : "Disabled",
  }));
}

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  if (!(await isLocalLibraryPreviewActive())) notFound();
  try {
    const adminPreview = (await searchParams).admin === "true";
    const [all, images, videos, documents, users] = await Promise.all([
      getDevMediaAssets({ pageSize: "25" }),
      getDevMediaAssets({ category: "image", pageSize: "25" }),
      getDevMediaAssets({ category: "video", pageSize: "25" }),
      getDevMediaAssets({ category: "document", pageSize: "25" }),
      adminPreview ? previewUsers() : Promise.resolve([]),
    ]);
    return <LocalPreviewClient catalog={{ all, images, videos, documents }} users={users} adminPreview={adminPreview} />;
  } catch {
    return <main className="kdiFatal" role="alert"><b>Media library unavailable</b><p>The read-only catalogue could not be loaded.</p></main>;
  }
}
