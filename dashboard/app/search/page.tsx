import { ApplicationShell, Crumbs } from "../application-shell";
import { requireProtectedPage } from "../auth";
import { SearchExperience } from "./search-experience";

export const dynamic = "force-dynamic";

export default async function SearchPage() {
  await requireProtectedPage();
  return (
    <ApplicationShell panel="staff" active="/search">
      <Crumbs items={[{ label: "Search" }]} />
      <header className="contentHead">
        <div>
          <span className="kicker">SEMANTIC MEDIA SEARCH</span>
          <h1>Search</h1>
          <p>Search by meaning across every enrolled asset. Each result shows how it matched.</p>
        </div>
      </header>
      <SearchExperience />
    </ApplicationShell>
  );
}
