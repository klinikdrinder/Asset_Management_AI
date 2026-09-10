export const RESULT_COUNT_IMPLEMENTATION_VERSION="kdi_result_count_controller_v1";

export type CanonicalResultRequest={
  requested_count:number|null;
  system_default_count:number;
  effective_count:number|"AMBIGUOUS";
};

export type ResultCountMetadata={
  requested_count:number|null;
  effective_count:number;
  returned_count:number;
  available_valid_count:number;
  count_source:"EXPLICIT"|"DEFAULT";
  count_clamped:boolean;
};

export function applyResultCount<T>(
  rankedCandidates:readonly T[],
  request:CanonicalResultRequest,
  options:{isAuthorized:(candidate:T)=>boolean;isEligible:(candidate:T)=>boolean},
):{candidates:T[];count:ResultCountMetadata}{
  const fallback=Math.max(1,Math.trunc(request.system_default_count));
  const effective=typeof request.effective_count==="number"&&Number.isFinite(request.effective_count)
    ?Math.max(1,Math.trunc(request.effective_count)):fallback;
  const valid=rankedCandidates.filter(candidate=>options.isAuthorized(candidate)&&options.isEligible(candidate));
  const candidates=valid.slice(0,effective);
  return{candidates,count:{requested_count:request.requested_count,effective_count:effective,
    returned_count:candidates.length,available_valid_count:valid.length,
    count_source:request.requested_count===null?"DEFAULT":"EXPLICIT",
    count_clamped:request.requested_count!==null&&request.requested_count!==effective}};
}
