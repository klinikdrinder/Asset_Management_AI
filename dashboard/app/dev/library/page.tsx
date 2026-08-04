import { notFound } from "next/navigation";
import { isLibraryDevBypassEnabled } from "../../lib/library/dev-bypass";
import { getDevMediaAssets } from "../../lib/media/dev-repository";
import { parseMediaQuery } from "../../lib/media/repository";
import { DevLibraryClient } from "./dev-library-client";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) { if (!isLibraryDevBypassEnabled()) notFound(); const query = await searchParams, parsed = parseMediaQuery(query); let result; try { result = await getDevMediaAssets(query); } catch { return DatabaseError(); } return <DevLibraryClient result={result} parsed={parsed} rawQuery={query} />; }
function DatabaseError() { return <main className="devFatal" role="alert"><b>Media database unavailable</b><p>The live Supabase catalogue could not be loaded. Check the server configuration and try again.</p></main>; }
