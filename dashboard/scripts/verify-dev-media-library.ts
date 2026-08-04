import "server-only";
import nextEnv from "@next/env";
nextEnv.loadEnvConfig(process.cwd());
const { getDevMediaAssets } = await import("../app/lib/media/dev-repository");
type Item = Awaited<ReturnType<typeof getDevMediaAssets>>["items"][number];
function assert(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
function compare(a: Item, b: Item, sort: "newest" | "oldest" | "largest" | "smallest") { const field = sort === "largest" || sort === "smallest" ? "sizeBytes" : "modifiedAt", av = a[field], bv = b[field]; if (av == null && bv == null) return a.id.localeCompare(b.id); if (av == null) return 1; if (bv == null) return -1; const delta = typeof av === "number" ? av - (bv as number) : String(av).localeCompare(String(bv)); return (sort === "newest" || sort === "largest" ? -delta : delta) || a.id.localeCompare(b.id); }
async function traverse(input: Record<string, string>) { const first = await getDevMediaAssets({ ...input, page: "1", pageSize: "100" }), items = [...first.items]; for (let page = 2; page <= first.totalPages; page++) items.push(...(await getDevMediaAssets({ ...input, page: String(page), pageSize: "100" })).items); return { first, items }; }
try {
  const defaultPage = await getDevMediaAssets(), finalPage = await getDevMediaAssets({ page: "36" });
  assert(defaultPage.pageSize === 25 && defaultPage.items.length === 25, "first_page_failed"); assert(finalPage.items.length === 3, "final_page_failed");
  const all = await traverse({ sort: "newest" }), ids = new Set(all.items.map(item => item.id)); assert(all.first.total === 878 && all.items.length === 878 && ids.size === 878, "pagination_traversal_failed");
  const categories = { image: 0, video: 0, document: 0, other: 0 }; for (const item of all.items) { categories[item.category]++; assert(Boolean(item.id && item.filename && item.category), "media_asset_mapping_failed"); }
  assert(categories.image === 290 && categories.video === 585 && categories.document === 3 && categories.other === 0, "category_counts_failed");
  for (const category of ["image", "video", "document"] as const) { const page = await getDevMediaAssets({ category }); assert(page.total === categories[category] && page.items.every(item => item.category === category), "category_filter_failed"); }
  const sample = all.items.find(item => item.extension && item.filename.length > 4); assert(sample, "filter_sample_unavailable");
  const extension = await getDevMediaAssets({ extension: sample.extension! }); assert(extension.total > 0 && extension.items.every(item => item.extension?.toLowerCase() === sample.extension?.toLowerCase()), "extension_filter_failed");
  const searchTerm = sample.filename.replace(/[^a-z0-9 ]/gi, " ").split(/\s+/).find(part => part.length >= 4); assert(searchTerm, "search_sample_unavailable"); const search = await getDevMediaAssets({ query: searchTerm }); assert(search.total > 0 && search.items.every(item => item.filename.toLowerCase().includes(searchTerm.toLowerCase())), "filename_search_failed");
  for (const sort of ["newest", "oldest", "largest", "smallest"] as const) { const result = sort === "newest" ? all : await traverse({ sort }); assert(result.items.every((item, index) => index === 0 || compare(result.items[index - 1], item, sort) <= 0), `${sort}_sort_failed`); }
  console.log("total_assets=878"); console.log("image_assets=290"); console.log("video_assets=585"); console.log("document_assets=3"); console.log("default_page_size=25"); console.log("total_pages=36"); console.log("pagination_unique=true"); console.log("search_filter_sort_mapping=true"); console.log("mock_fallback=false"); console.log("DEV_MEDIA_LIBRARY_INTEGRATION_PASSED");
} catch (error) { console.error(error instanceof Error ? error.message : "dev_media_library_verification_failed"); process.exitCode = 1; }
