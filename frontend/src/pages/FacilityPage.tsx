import { ArrowDown, Check, Package, Radio, ShieldCheck, Smartphone } from "lucide-react";

import { PageState } from "../components/PageState";
import { StatusPill } from "../components/StatusPill";
import { useTulina } from "../state/TulinaContext";

export function FacilityPage() {
  const { overview, online } = useTulina();
  const busiu = overview?.network.find((row) => row.facility_id === "F02" && row.product_id === "P05");
  return (
    <PageState>
      {overview && busiu ? (
        <div className="page facility-page">
          <section className="page-title-row">
            <div><span className="eyebrow">Facility phone</span><h1>Busiu receiving view</h1><p>The same recommendation, simplified for the designated facility worker.</p></div>
            <div className="device-label"><Smartphone aria-hidden="true" /><span>DEV-F02-01</span></div>
          </section>
          <div className="phone-stage">
            <div className="phone-frame">
              <div className="phone-speaker" aria-hidden="true" />
              <div className="phone-screen">
                <header><div><span>Busiu Health Centre IV</span><strong>Medicine receiving</strong></div><div className={online ? "phone-online" : "phone-offline"}><Radio size={13} />{online ? "Online" : "Offline"}</div></header>
                <main>
                  <span className="section-kicker">Current stock</span>
                  <h2>{overview.recommendation.product_name}</h2>
                  <div className="stock-number"><strong>{busiu.on_hand}</strong><span>pack on hand<br />{busiu.days_of_cover} days of cover</span></div>
                  <div className="low-stock-bar"><span style={{ width: `${Math.max(8, busiu.days_of_cover / 0.6)}%` }} /></div>
                  <div className="phone-divider"><ArrowDown size={17} aria-hidden="true" /><span>Tulina found stock nearby</span></div>
                  <article className="incoming-card">
                    <StatusPill status={overview.recommendation.status} />
                    <div className="incoming-quantity"><Package aria-hidden="true" /><strong>11 packs</strong></div>
                    <h3>From Mbale RRH</h3>
                    <p>Oxytocin · batch {overview.recommendation.batch_number}</p>
                    <ul><li><ShieldCheck size={15} /> Cold chain checked</li><li><Check size={15} /> Restores 60 days of cover</li></ul>
                  </article>
                  {overview.recommendation.status === "APPROVED" ? <div className="phone-success"><Check size={18} /><span><strong>DHO approved</strong>Waiting for the Tulina Note to be prepared</span></div> : <p className="phone-help">The District Health Officer must approve before this medicine can be prepared for collection.</p>}
                </main>
                <footer>Tulina · synthetic demo</footer>
              </div>
            </div>
            <aside className="phone-explainer"><span className="section-kicker">Designed for the receiving moment</span><h2>Only what the worker needs</h2><p>Clear medicine, quantity, source, safety state, and approval—without exposing private district stock calculations.</p><ul><li>Large, touch-friendly controls</li><li>Network state always visible</li><li>Technical evidence stays behind the district view</li></ul></aside>
          </div>
        </div>
      ) : null}
    </PageState>
  );
}
