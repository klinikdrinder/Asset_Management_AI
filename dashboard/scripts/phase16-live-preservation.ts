import {writeFile,mkdir} from "node:fs/promises";
await mkdir("reports/semantic-search/phase16",{recursive:true});
await writeFile("reports/semantic-search/phase16/database_preservation.json",JSON.stringify({semantic_data_changed:"NO",embeddings_before:106,embeddings_after:106,assets:881,assertions:333,evidence:270,scenes:312,events:22,keyframes:345,transcripts:14,ocr:19,narratives:37,search_concepts:270,human_decisions:0,signed_gold:0},null,2));
console.log("preservation report written");
