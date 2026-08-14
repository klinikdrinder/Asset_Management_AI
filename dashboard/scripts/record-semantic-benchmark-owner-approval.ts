import { recordBenchmarkOwnerApproval } from "../app/lib/semantic-review/manifest";

console.log(JSON.stringify(await recordBenchmarkOwnerApproval(),null,2));
