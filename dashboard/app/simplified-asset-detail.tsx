import{ApplicationShell,Status}from"./application-shell";
import{fileKind,formatBytes,maskFilename}from"./lib";
import{getPreviewRole}from"./lib/dev-preview";
import{MediaViewer}from"./media-viewer";
import{getFileById,getAssetSemanticDetail}from"./queries";
import{AssetSemanticPanel}from"./asset-semantic-panel";
import{SceneTimeline}from"./scene-timeline";
import{notFound}from"next/navigation";

export async function SimplifiedAssetDetail({id}:{id:string}){
  const[file,previewRole]=await Promise.all([getFileById(id),getPreviewRole()]);
  if(!file.data)notFound();
  const asset=file.data;const kind=fileKind(asset.mime,asset.extension);
  const detail=(await getAssetSemanticDetail(asset.assetId)).data??{layers:[],scenes:[]};
  const verified=asset.migration==="VERIFIED";
  const download=previewRole?"/api/dev-preview/download":verified?`/api/media/${asset.id}/download`:null;
  const assetDate=asset.modified||asset.created;
  const hasSemanticMetadata=Boolean(asset.contentType||asset.treatment||asset.subject||asset.doctorName||asset.aiDescription);
  return <ApplicationShell panel="staff" active="/library"><a className="backLink" href="/library">← Back to library</a><article className="assetDetail">{!previewRole&&verified?<MediaViewer id={asset.id} kind={kind} extension={asset.extension||""}/>:<div className={`assetPreview ${kind}`}><span>{kind==="image"?"IMAGE PREVIEW":kind==="video"?"VIDEO PREVIEW":"FILE PREVIEW"}</span></div>}<div className="assetInfo"><Status value={asset.decision==="TAKE"?"APPROVED":"RESTRICTED"}/><h1>{maskFilename(asset.name)}</h1><p className="assetDescription">{asset.shortCaption||`Approved central-library media from ${asset.folderName}.`}</p><dl><div><dt>Type</dt><dd>{asset.mime||asset.extension||"File"}</dd></div><div><dt>Size</dt><dd>{formatBytes(asset.size)}</dd></div><div><dt>Date</dt><dd>{assetDate?new Date(assetDate).toLocaleDateString("en-MY"):"Date unavailable"}</dd></div><div><dt>Source</dt><dd>{asset.folderName}</dd></div></dl>{hasSemanticMetadata&&<div className="semanticMetadata"><h3>AI search metadata</h3><dl>{asset.contentType&&<div><dt>Content type</dt><dd>{asset.contentType}</dd></div>}{asset.treatment&&<div><dt>Treatment</dt><dd>{asset.treatment}</dd></div>}{asset.subject&&<div><dt>Subject</dt><dd>{asset.subject}</dd></div>}{asset.doctorName&&<div><dt>Doctor</dt><dd>{asset.doctorName}</dd></div>}</dl>{asset.aiDescription&&<p>{asset.aiDescription}</p>}</div>}{download?<a className="primaryLink" href={download}>Download</a>:<button disabled>Download unavailable</button>}</div>{kind==="video"&&detail.scenes.length>0&&<SceneTimeline scenes={detail.scenes}/>}<AssetSemanticPanel detail={detail}/></article></ApplicationShell>;
}
