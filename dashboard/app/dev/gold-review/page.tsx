import { notFound } from "next/navigation";
import { goldReviewEnabled,listPackets } from "../../lib/gold-review/store";
import { GoldReviewClient } from "./gold-review-client";
export const dynamic="force-dynamic";
export default async function Page(){if(!goldReviewEnabled())notFound();return <GoldReviewClient initialPackets={await listPackets()}/>}
