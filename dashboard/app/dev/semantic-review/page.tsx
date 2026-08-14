import { notFound } from "next/navigation";
import { isLibraryDevBypassEnabled } from "../../lib/library/dev-bypass";
import { CONTENT_TYPES, loadReviewManifest, validatePending } from "../../lib/semantic-review/manifest";
import { SemanticReviewClient } from "./semantic-review-client";
export const dynamic="force-dynamic";
export default async function Page(){if(!isLibraryDevBypassEnabled())notFound();const manifest=await loadReviewManifest();return <SemanticReviewClient initialAssets={manifest.assets} initialValidation={validatePending(manifest.assets)} contentTypes={[...CONTENT_TYPES]}/>}
