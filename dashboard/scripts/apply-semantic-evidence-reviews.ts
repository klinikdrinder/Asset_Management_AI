import { correctReviewedAssetEvidence, loadReviewManifest, saveEvidenceReview } from "../app/lib/semantic-review/manifest";

const reviews = [
  ["0260a986-3b66-42c6-9ec6-d6cc50a56584", {content_type:"Other",treatment:"",subject:"Patient facial close-up",doctor_name:"",ai_description:"Close-up clinical photograph of a patient’s face while seated for assessment or treatment.",short_caption:"Patient facial close-up"}],
  ["133c5486-1531-486b-ae48-acc5391d46b5", {content_type:"Treatment Result",treatment:"",subject:"Patient frontal hairline",doctor_name:"",ai_description:"Side-profile follow-up image showing a patient’s closely shaved scalp and frontal hairline.",short_caption:"Frontal hairline follow-up"}],
  ["c392a71d-3f01-4879-b7b0-5da2104ad9e7", {content_type:"Treatment Result",treatment:"",subject:"Patient crown and scalp",doctor_name:"",ai_description:"Overhead image showing a patient’s crown with visible scalp and reduced hair density.",short_caption:"Crown and scalp image"}],
  ["7acbf067-1769-41fc-baef-554e0c9768cf", {content_type:"Treatment Result",treatment:"",subject:"Patient frontal hairline",doctor_name:"",ai_description:"Side-profile clinical image showing a patient’s frontal hairline with the hair held back.",short_caption:"Frontal hairline image"}],
  ["8a34e00e-8f33-4591-8692-fb9358cb72d6", {content_type:"Treatment Result",treatment:"Hair transplant",subject:"Patient scalp after hair transplant",doctor_name:"",ai_description:"Post-procedure image showing implanted graft sites across a patient’s shaved frontal and top scalp.",short_caption:"Post-transplant scalp"}],
  ["811b3783-8b55-4537-a825-435967910f23", {content_type:"Treatment Result",treatment:"",subject:"Patient crown and scalp",doctor_name:"",ai_description:"Overhead follow-up image showing a patient’s closely shaved crown and visible scalp.",short_caption:"Crown follow-up image"}],
  ["029c7315-b1a6-41f6-bb48-f1a91b492571", {content_type:"Treatment Procedure",treatment:"",subject:"Clinician performing facial procedure",doctor_name:"",ai_description:"A clinician applies a handheld treatment device to a patient’s forehead while the patient wears protective eye shields.",short_caption:"Facial treatment procedure"}],
  ["ff589be5-5f62-4adc-bffd-4755cd232a0b", {content_type:"Other",treatment:"",subject:"Clinic staff member on camera",doctor_name:"",ai_description:"A clinic staff member wearing scrubs and a surgical cap looks toward the camera.",short_caption:"Clinic staff on camera"}],
  ["05c43d14-c1dc-4e78-bf88-0ef8ddbcd443", {content_type:"Treatment Procedure",treatment:"",subject:"Patient undergoing scalp injections",doctor_name:"",ai_description:"A clinician administers injections to a patient’s scalp during a clinical hair treatment.",short_caption:"Scalp injection procedure"}],
  ["ccfc6b3d-03fa-4261-b8df-cb23fe52716f", {content_type:"Treatment Procedure",treatment:"",subject:"Clinician performing facial procedure",doctor_name:"",ai_description:"A clinician applies a handheld treatment device to a patient’s face while the patient wears protective eye shields.",short_caption:"Facial treatment procedure"}],
  ["c0bca228-da4b-441c-8011-1b54e9f672cf", {content_type:"Treatment Procedure",treatment:"",subject:"Patient undergoing facial procedure",doctor_name:"",ai_description:"A clinician administers an injection near a patient’s jaw while a handheld device is applied to the forehead.",short_caption:"Facial treatment procedure"}],
  ["3059f085-aaea-418a-8ef4-a8cba2393065", {content_type:"Treatment Procedure",treatment:"",subject:"Patient undergoing scalp injections",doctor_name:"",ai_description:"A clinician administers injections to a seated patient’s scalp during a clinical hair treatment.",short_caption:"Scalp injection procedure"}],
  ["930417e8-24c9-4d51-9d30-ce4da96638df", {content_type:"Treatment Procedure",treatment:"",subject:"Patient undergoing scalp injections",doctor_name:"",ai_description:"A clinician administers injections across a seated patient’s scalp during a clinical hair treatment.",short_caption:"Scalp injection procedure"}],
  ["258b358e-5c7c-47a4-a195-087a203a7bfd", {content_type:"Treatment Procedure",treatment:"",subject:"Clinician performing facial procedure",doctor_name:"",ai_description:"A clinician treats a patient’s face with a handheld treatment device while the patient wears protective eye shields.",short_caption:"Facial treatment procedure"}],
] as const;

for (const [assetId, fields] of reviews) {
  const saved = await saveEvidenceReview(assetId, fields);
  if (saved.asset_id !== assetId || saved.reviewed_by !== "Codex-assisted evidence review") throw new Error(`Review read-back failed for ${assetId}`);
}

await correctReviewedAssetEvidence("37fac28d-7dfc-4450-b6dd-27f671294102", {
  content_type:"Treatment Result",treatment:"",subject:"Patient frontal scalp and hairline",doctor_name:"",
  ai_description:"Top-down clinical image showing a patient’s frontal scalp, hairline, and reduced hair density.",short_caption:"Frontal scalp and hairline",
});

const manifest=await loadReviewManifest();
const reviewed=manifest.assets.slice(5).filter(row=>Boolean(row.reviewed_by&&row.reviewed_at));
if(reviewed.length!==15)throw new Error(`Expected 15 reviewed assets, found ${reviewed.length}`);
console.log(JSON.stringify({saved:reviews.length,corrected:1,reviewed:reviewed.length},null,2));
