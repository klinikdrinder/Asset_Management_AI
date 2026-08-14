import { notFound } from "next/navigation";
import { isLibraryDevBypassEnabled } from "../../lib/library/dev-bypass";
import { getDevMediaAssets } from "../../lib/media/dev-repository";
import { parseMediaQuery } from "../../lib/media/repository";
import { DevLibraryClient } from "./dev-library-client";
import { DeterministicQueryInterpreter, stateFromSearchParams } from "../../lib/media/conversation";
import { LibrarySearchBox } from "../../library-search-box";
export const dynamic = "force-dynamic";
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) { if (!isLibraryDevBypassEnabled()) notFound(); const query=await searchParams,previous=stateFromSearchParams(query),conversation=query.refine?(await new DeterministicQueryInterpreter().interpret(query.refine,previous)).state:previous,filters={...query};for(const key of Object.keys(filters))if(key==="refine"||key==="nlq"||key.startsWith("cs_"))delete filters[key];if(conversation.mediaType)filters.category=conversation.mediaType;if(conversation.sort!=="relevance")filters.sort=conversation.sort;const parsed=parseMediaQuery(filters);let result;try{result=await getDevMediaAssets(filters)}catch{return DatabaseError()}return <><div className="devConversationPanel"><LibrarySearchBox parsed={parsed} conversation={conversation} action="/dev/library"/></div><DevLibraryClient result={result} parsed={parsed} rawQuery={query}/></>; }
function DatabaseError() { return <main className="devFatal" role="alert"><b>Media database unavailable</b><p>The live Supabase catalogue could not be loaded. Check the server configuration and try again.</p></main>; }
