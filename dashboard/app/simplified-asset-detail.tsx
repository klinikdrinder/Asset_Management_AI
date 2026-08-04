import{ApplicationShell,Status}from"./application-shell";
import{fileKind,formatBytes,maskFilename}from"./lib";
import{getPreviewRole}from"./lib/dev-preview";
import{getFileById}from"./queries";
import{notFound}from"next/navigation";

export async function SimplifiedAssetDetail({id}:{id:string}){
  const[file,previewRole]=await Promise.all([getFileById(id),getPreviewRole()]);
  if(!file.data)notFound();
  const asset=file.data;const kind=fileKind(asset.mime,asset.extension);
  const download=previewRole?"/api/dev-preview/download":asset.destinationId?`/api/media/${asset.assetId}/download`:null;
  const assetDate=asset.modified||asset.created;
  return <ApplicationShell panel="staff" active="/library"><a className="backLink" href="/library">← Back to library</a><article className="assetDetail"><div className={`assetPreview ${kind}`}><span>{kind==="image"?"IMAGE PREVIEW":kind==="video"?"VIDEO PREVIEW":"FILE PREVIEW"}</span></div><div className="assetInfo"><Status value={asset.decision==="TAKE"?"APPROVED":"RESTRICTED"}/><h1>{maskFilename(asset.name)}</h1><p className="assetDescription">Approved central-library media from {asset.folderName}.</p><dl><div><dt>Type</dt><dd>{asset.mime||asset.extension||"File"}</dd></div><div><dt>Size</dt><dd>{formatBytes(asset.size)}</dd></div><div><dt>Date</dt><dd>{assetDate?new Date(assetDate).toLocaleDateString("en-MY"):"Date unavailable"}</dd></div><div><dt>Source</dt><dd>{asset.folderName}</dd></div></dl>{download?<a className="primaryLink" href={download}>Download</a>:<button disabled>Download unavailable</button>}</div></article></ApplicationShell>;
}
