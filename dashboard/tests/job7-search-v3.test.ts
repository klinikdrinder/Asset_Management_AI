import assert from "node:assert/strict";
import test from "node:test";
import { interpretV3Query, V3_RANKING } from "../app/lib/media/search-v3";

test("V3 defaults to five and resolves controlled intent", () => {
  const q=interpretV3Query("close-up video of a clinician examining the frontal scalp");
  assert.equal(q.requestedCount,5); assert.equal(q.filters.media_type,"video");
  assert.equal(q.filters.role,"CLINICIAN_LIKE"); assert.equal(q.filters.action,"EXAMINING");
  assert.equal(q.filters.anatomy,"FRONTAL_SCALP"); assert.equal(q.filters.shot_type,"CLOSEUP");
});
test("explicit count is bounded",()=>{
  assert.equal(interpretV3Query("show me 12 videos").requestedCount,12);
  assert.equal(interpretV3Query("show me 999 videos").requestedCount,50);
});
test("subject age is not interpreted as a result count",()=>{
  const q=interpretV3Query("male over 30 years old doing hair transplant");
  assert.equal(q.requestedCount,5); assert.equal(q.countExplicit,false);
});
test("next results preserve context and exclude returned assets",()=>{
  const q=interpretV3Query("next 5",{resolvedQuery:"clinic footage",filters:{media_type:"video"},requestedCount:5,returnedAssetIds:["a","b","a"]});
  assert.equal(q.queryType,"NEXT_RESULTS"); assert.equal(q.resolvedQuery,"clinic footage");
  assert.deepEqual(q.excludedAssetIds,["a","b"]); assert.equal(q.filters.media_type,"video");
});
test("refinement preserves semantic context",()=>{
  const q=interpretV3Query("only close-ups",{resolvedQuery:"hair treatment footage",filters:{media_type:"video"},requestedCount:5});
  assert.equal(q.queryType,"REFINEMENT"); assert.equal(q.resolvedQuery,"hair treatment footage"); assert.equal(q.filters.shot_type,"CLOSEUP");
});
test("ranking is normalized and filename is weakest",()=>{
  const total=V3_RANKING.structured+V3_RANKING.visualScene+V3_RANKING.visualAsset+V3_RANKING.lexicalAsset+V3_RANKING.lexicalScene+V3_RANKING.visualKeyframe+V3_RANKING.filename;
  assert.ok(Math.abs(total-1)<1e-9); assert.ok(V3_RANKING.filename<V3_RANKING.lexicalScene); assert.equal(V3_RANKING.maximumResults,50);
});
