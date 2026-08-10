import { ArrowRight, Check, Clock3, Route, ShieldCheck, ThermometerSnowflake } from "lucide-react";

import { useTulina } from "../state/TulinaContext";
import type { Recommendation } from "../types";
import { StatusPill } from "./StatusPill";

export function RecommendationCard({ recommendation }: { recommendation: Recommendation }) {
  const { busy, role, requestApproval, approve } = useTulina();
  const handleRequest = () => void requestApproval().catch(() => undefined);
  const handleApprove = () => void approve().catch(() => undefined);
  return (
    <article className="recommendation-card">
      <header>
        <div>
          <span className="section-kicker">{recommendation.transfer_id}</span>
          <h2>Found nearby</h2>
        </div>
        <StatusPill status={recommendation.status} />
      </header>
      <div className="transfer-route" aria-label={`${recommendation.donor_name} to ${recommendation.recipient_name}`}>
        <div>
          <span>From</span>
          <strong>{recommendation.donor_short_name}</strong>
          <small>{recommendation.evidence.donor_on_hand} packs on hand</small>
        </div>
        <div className="route-line" aria-hidden="true">
          <span />
          <ArrowRight size={18} />
        </div>
        <div>
          <span>To</span>
          <strong>{recommendation.recipient_short_name}</strong>
          <small>{recommendation.evidence.recipient_cover_before_days} days of cover</small>
        </div>
      </div>
      <div className="medicine-row">
        <div className="quantity-seal">
          <strong>{recommendation.quantity}</strong>
          <span>{recommendation.transfer_unit}s</span>
        </div>
        <div>
          <h3>{recommendation.product_name}</h3>
          <p>
            Batch {recommendation.batch_number} · expires {new Date(recommendation.evidence.expiry_date).toLocaleDateString("en-GB", { month: "short", year: "numeric" })}
          </p>
        </div>
      </div>
      <div className="decision-strip">
        <span><Route size={16} aria-hidden="true" /> {recommendation.evidence.route_km} km · {recommendation.evidence.route_minutes} min</span>
        <span><ThermometerSnowflake size={16} aria-hidden="true" /> Cold chain ready</span>
        <span><ShieldCheck size={16} aria-hidden="true" /> All 5 safety checks passed</span>
      </div>
      <details className="decision-details">
        <summary>How Tulina decided</summary>
        <div className="evidence-grid">
          <div>
            <span>Donor cover after</span>
            <strong>{recommendation.evidence.donor_cover_after_days} days</strong>
          </div>
          <div>
            <span>Busiu cover after</span>
            <strong>{recommendation.evidence.recipient_cover_after_days} days</strong>
          </div>
          <div>
            <span>Expiry risk protected</span>
            <strong>{recommendation.metrics.projected_expiry_risk_avoided} packs</strong>
          </div>
        </div>
        <ul>
          {recommendation.policy.reasons.map((reason) => (
            <li key={reason}><Check size={14} aria-hidden="true" /> {reason}</li>
          ))}
        </ul>
        <p className="technical-note">Calculation contract v{recommendation.schema_version} · deterministic stock, FEFO, route and policy tools</p>
      </details>
      <footer className="card-actions">
        {recommendation.status === "FOUND" ? (
          <button className="button primary" disabled={busy} onClick={handleRequest}>
            <Clock3 size={16} aria-hidden="true" /> Request DHO approval
          </button>
        ) : null}
        {recommendation.status === "AWAITING_APPROVAL" ? (
          <button className="button approve" disabled={busy} onClick={handleApprove}>
            <Check size={16} aria-hidden="true" /> Approve as DHO
          </button>
        ) : null}
        {recommendation.status === "APPROVED" ? (
          <div className="approval-record">
            <Check size={18} aria-hidden="true" />
            <span><strong>Approved by District Health Officer</strong>APR-DHO-001 · ready for dispatch preparation</span>
          </div>
        ) : null}
        <span className="role-hint">Acting as {role.replaceAll("_", " ")}</span>
      </footer>
    </article>
  );
}
