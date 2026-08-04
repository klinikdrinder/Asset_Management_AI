import { requireProtectedPage } from "../auth";
import { getPreviewRole } from "../lib/dev-preview";
import { MediaLibraryPage } from "../media-library-page";
import { PreviewLibrary } from "../preview/preview-library";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) { await requireProtectedPage(); const preview = await getPreviewRole(); return preview ? <PreviewLibrary role={preview} /> : <MediaLibraryPage query={await searchParams} />; }
