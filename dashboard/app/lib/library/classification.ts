export const MEDIA_CATEGORIES=["image","video","document","other"]as const;
export type MediaCategory=typeof MEDIA_CATEGORIES[number];
const IMAGE_EXTENSIONS=new Set(["jpg","jpeg","png","webp"]);
const VIDEO_EXTENSIONS=new Set(["mp4","mov"]);
const DOCUMENT_EXTENSIONS=new Set(["pdf","pptx"]);
const PDF="application/pdf",PPTX="application/vnd.openxmlformats-officedocument.presentationml.presentation";
export function normalizeExtension(value:string|null|undefined){return(value??"").trim().replace(/^\./,"").toLowerCase()}
export function classifyMedia(mime:string|null|undefined,extension:string|null|undefined):MediaCategory{const m=(mime??"").trim().toLowerCase(),e=normalizeExtension(extension);if(m.startsWith("image/"))return"image";if(m.startsWith("video/"))return"video";if(m===PDF||m===PPTX||m.includes("presentation"))return"document";if(IMAGE_EXTENSIONS.has(e))return"image";if(VIDEO_EXTENSIONS.has(e))return"video";if(DOCUMENT_EXTENSIONS.has(e))return"document";return"other"}
export function categoryRestFilter(category:MediaCategory){if(category==="image")return"or=(mime_type.ilike.image/*,file_extension.in.(jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP))";if(category==="video")return"or=(mime_type.ilike.video/*,file_extension.in.(mp4,mov,MP4,MOV))";if(category==="document")return`or=(mime_type.eq.${PDF},mime_type.eq.${PPTX},mime_type.ilike.*presentation*,file_extension.in.(pdf,pptx,PDF,PPTX))`;return"and=(mime_type.not.ilike.image/*,mime_type.not.ilike.video/*,mime_type.not.ilike.*presentation*,mime_type.neq.application/pdf,mime_type.neq.application/vnd.openxmlformats-officedocument.presentationml.presentation,file_extension.not.in.(jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP,mp4,mov,MP4,MOV,pdf,pptx,PDF,PPTX))"}
