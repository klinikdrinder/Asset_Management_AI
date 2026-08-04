export type DemoAsset={id:string;name:string;kind:"image"|"video"|"document";extension:string;size:number;date:string;source:string;status:"APPROVED"|"RESTRICTED";description:string;duration?:string};
export const DEMO_SOURCES=["ALL PATIENT REVIEW","Nushad Raw Video","Photo/Video for Marketing"]as const;
export const INITIAL_DEMO_ASSETS:DemoAsset[]=[
{id:"demo-brand-portrait",name:"DEMO DATA — Brand portrait.jpg",kind:"image",extension:"JPG",size:2480000,date:"2026-08-04",source:DEMO_SOURCES[2],status:"APPROVED",description:"Approved marketing portrait for internal campaign use."},
{id:"demo-training-video",name:"DEMO DATA — Training overview.mp4",kind:"video",extension:"MP4",size:18430000,date:"2026-08-03",source:DEMO_SOURCES[1],status:"APPROVED",description:"Synthetic training video prepared for frontend review.",duration:"02:18"},
{id:"demo-clinical-image",name:"DEMO DATA — Restricted clinical image.png",kind:"image",extension:"PNG",size:3240000,date:"2026-08-02",source:DEMO_SOURCES[0],status:"RESTRICTED",description:"Synthetic restricted example. No patient information is present."},
{id:"demo-campaign-video",name:"DEMO DATA — Campaign launch.mov",kind:"video",extension:"MOV",size:24680000,date:"2026-08-01",source:DEMO_SOURCES[2],status:"APPROVED",description:"Synthetic campaign motion asset.",duration:"00:42"},
{id:"demo-brief",name:"DEMO DATA — Media brief.pdf",kind:"document",extension:"PDF",size:840000,date:"2026-07-30",source:DEMO_SOURCES[2],status:"APPROVED",description:"Synthetic media brief used for interface testing."},
];
export const DEMO_ACTIVITY=[
{id:"activity-1",type:"completed",title:"Marketing image synchronized",detail:"Demo migration completed successfully",assetId:"demo-brand-portrait"},
{id:"activity-2",type:"attention",title:"Video metadata needs review",detail:"Demo retry is available",assetId:"demo-training-video"},
{id:"activity-3",type:"duplicate",title:"Exact duplicate detected",detail:"Existing master asset retained",assetId:"demo-brand-portrait"},
{id:"activity-4",type:"unsupported",title:"Unsupported archive skipped",detail:"No production file was changed"},
]as const;
