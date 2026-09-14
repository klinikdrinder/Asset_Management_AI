export type ManagementRole="super_admin"|"admin"|"user";
export type ManagedRole=Exclude<ManagementRole,"super_admin">;
export function canAccessAdministration(role:ManagementRole){return role==="super_admin"||role==="admin"}
export function canUpload(role:ManagementRole){return role==="super_admin"||role==="admin"}
export function canInvite(actor:ManagementRole,requested:unknown):requested is ManagedRole{return actor==="super_admin"?(requested==="admin"||requested==="user"):actor==="admin"&&requested==="user"}
export function canManage(actor:ManagementRole,target:ManagementRole){return actor==="super_admin"?target!=="super_admin":actor==="admin"&&target==="user"}
export function allowedInvitationRoles(actor:ManagementRole):ManagedRole[]{return actor==="super_admin"?["user","admin"]:actor==="admin"?["user"]:[]}
