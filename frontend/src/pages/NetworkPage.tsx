import { Building2, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { PageState } from "../components/PageState";
import { useTulina } from "../state/TulinaContext";

export function NetworkPage() {
  const { overview } = useTulina();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("attention");
  const positions = useMemo(() => {
    if (!overview) return [];
    return overview.network.filter((row) => {
      const matchesQuery = `${row.facility_name} ${row.product_name}`.toLowerCase().includes(query.toLowerCase());
      const matchesFilter = filter === "all" || (filter === "attention" ? row.state !== "covered" : row.state === filter);
      return matchesQuery && matchesFilter;
    });
  }, [overview, query, filter]);
  return (
    <PageState>
      {overview ? (
        <div className="page network-page">
          <section className="page-title-row">
            <div>
              <span className="eyebrow">District View</span>
              <h1>Stock network</h1>
              <p>Needs and safe surplus calculated from 70 synthetic facility-product positions.</p>
            </div>
            <div className="network-summary"><Building2 aria-hidden="true" /><strong>7 facilities</strong><span>10 essential medicines</span></div>
          </section>
          <div className="toolbar">
            <label className="search-field"><Search size={17} aria-hidden="true" /><span className="sr-only">Search positions</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search facility or medicine" /></label>
            <label><span className="sr-only">Filter status</span><select value={filter} onChange={(event) => setFilter(event.target.value)}><option value="attention">Needs attention</option><option value="needs_stock">Needs stock</option><option value="safe_surplus">Safe surplus</option><option value="all">All positions</option></select></label>
          </div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Facility</th><th>Medicine</th><th>On hand</th><th>Cover</th><th>Signal</th></tr></thead>
              <tbody>
                {positions.map((row) => (
                  <tr key={`${row.facility_id}-${row.product_id}`} className={row.facility_id === "F01" && row.product_id === "P05" || row.facility_id === "F02" && row.product_id === "P05" ? "highlight-row" : ""}>
                    <td><strong>{row.facility_short_name}</strong><span>{row.facility_id}</span></td>
                    <td><strong>{row.product_name}</strong><span>{row.product_id}</span></td>
                    <td>{row.on_hand} packs</td><td>{row.days_of_cover} days</td>
                    <td><span className={`signal signal-${row.state}`}>{row.state === "needs_stock" ? `Needs ${row.need_quantity}` : row.state === "safe_surplus" ? `Can safely share ${row.safe_release_quantity}` : "Covered"}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {positions.length === 0 ? <div className="empty-state">No stock positions match this view.</div> : null}
          </div>
          <p className="data-disclaimer">Synthetic operational balances for software demonstration and acceptance testing only.</p>
        </div>
      ) : null}
    </PageState>
  );
}
