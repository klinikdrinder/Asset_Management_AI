export const REVIEWER = "Nusaiba";
export const EVIDENCE_REVIEWER = "Codex-assisted evidence review";
export const REVIEWERS = [REVIEWER, EVIDENCE_REVIEWER] as const;
export const CONTENT_TYPES = ["Before & After","Treatment Result","Patient Testimonial","Doctor Explanation","Treatment Procedure","Consultation","Educational Video","Clinic Environment","Promotional Content","Doctor Talking","Patient Interview","Other"] as const;
export const REVIEW_FIELDS = ["content_type","treatment","subject","doctor_name","ai_description","short_caption"] as const;
export type ReviewAsset = { asset_id:string; filename:string; media_type:"image"|"video"; content_type:string; treatment:string; subject:string; doctor_name:string; ai_description:string; short_caption:string; reviewed_by:string; reviewed_at:string; description_provider?:string; description_model?:string; description_version?:string; evidence_reviewed_by?:string; evidence_reviewed_at?:string; owner_approved_by?:string; owner_approved_at?:string };
export type ReviewValidation = { existing_complete:number; new_reviewed:number; pending:number; valid:number; invalid:number; ready_for_manual_import:boolean; entries:{asset_id:string;filename:string;status:"complete"|"incomplete"|"invalid";errors:string[]}[] };
export function validateReviewFields(fields:Pick<ReviewAsset,"content_type"|"ai_description"|"short_caption">){
  if(!fields.content_type.trim())return "Missing required field: content_type";
  if(!CONTENT_TYPES.includes(fields.content_type.trim() as never))return "Invalid content type";
  if(!fields.ai_description.trim())return "Missing required field: description";
  if(!fields.short_caption.trim())return "Missing required field: short_caption";
  return null;
}
export function isApprovedReviewer(value:string){return (REVIEWERS as readonly string[]).includes(value)}
export function isReviewed(row:ReviewAsset){return isApprovedReviewer(row.reviewed_by)&&Boolean(row.reviewed_at)&&!Number.isNaN(Date.parse(row.reviewed_at))}
export function validatePending(assets:ReviewAsset[]):ReviewValidation{
  const entries=assets.slice(5).map(row=>{const errors:string[]=[];if(!CONTENT_TYPES.includes(row.content_type as never))errors.push("Content type is required");if(!row.ai_description.trim())errors.push("Description is required");if(!row.short_caption.trim())errors.push("Short caption is required");if(!isApprovedReviewer(row.reviewed_by))errors.push("Approved review provenance is required");if(!row.reviewed_at.trim()||Number.isNaN(Date.parse(row.reviewed_at)))errors.push("A valid review timestamp is required");return{asset_id:row.asset_id,filename:row.filename,status:(errors.length?(row.reviewed_by||row.reviewed_at||row.content_type||row.ai_description||row.short_caption?"invalid":"incomplete"):"complete") as "complete"|"incomplete"|"invalid",errors}});
  const newReviewed=entries.filter(x=>x.status==="complete").length,invalid=entries.filter(x=>x.status==="invalid").length,pending=entries.length-newReviewed-invalid;
  return{existing_complete:assets.slice(0,5).filter(isReviewed).length,new_reviewed:newReviewed,pending,valid:newReviewed,invalid,ready_for_manual_import:newReviewed===15&&invalid===0,entries};
}
