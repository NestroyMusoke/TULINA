import { AlertTriangle, Fingerprint, ShieldCheck, UserCheck } from "lucide-react";

import { ActivityTimeline } from "../components/ActivityTimeline";
import { FleetProgress } from "../components/FleetProgress";
import { PageState } from "../components/PageState";
import { useTulina } from "../state/TulinaContext";

export function AuditPage() {
  const { overview } = useTulina();
  const audit = overview?.governance.audit_chain;
  return (
    <PageState>
      {overview ? (
        <div className="page audit-page">
          <section className="page-title-row">
            <div>
              <span className="eyebrow">Audit view</span>
              <h1>Every decision leaves a record</h1>
              <p>Concise operational evidence and tool events—never hidden model reasoning.</p>
            </div>
            <div className={`chain-status ${audit?.verified ? "verified" : "failed"}`}>
              {audit?.verified ? <ShieldCheck aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
              <strong>{audit?.verified ? "Chain verified" : "Chain needs review"}</strong>
              <span>{audit?.event_count ?? 0} SHA-256 linked events</span>
            </div>
          </section>
          <FleetProgress detail={overview.agent_run} />
          <section className="governance-grid" aria-label="Governance controls">
            <article>
              <ShieldCheck aria-hidden="true" />
              <div>
                <span>Audit head</span>
                <strong>{audit?.head_hash.slice(0, 18)}…</strong>
                <small>Recomputed by the server, not assumed by this screen</small>
              </div>
            </article>
            <article>
              <UserCheck aria-hidden="true" />
              <div>
                <span>Human authority</span>
                <strong>DHO approval required</strong>
                <small>Agents can propose; only the named DHO approves</small>
              </div>
            </article>
            <article className={overview.governance.unresolved_exceptions ? "needs-review" : ""}>
              <AlertTriangle aria-hidden="true" />
              <div>
                <span>Exceptions</span>
                <strong>
                  {overview.governance.unresolved_exceptions
                    ? `${overview.governance.unresolved_exceptions} needs human review`
                    : "No open conflicts"}
                </strong>
                <small>Review never applies an extra stock mutation</small>
              </div>
            </article>
          </section>
          <div className="audit-grid">
            <section className="activity-section">
              <div className="section-heading"><span className="section-kicker">Human-readable</span><h2>Activity timeline</h2></div>
              <ActivityTimeline events={overview.activity} limit={20} />
            </section>
            <section className="audit-records">
              <div className="section-heading"><span className="section-kicker">Technical proof</span><h2>Event records</h2></div>
              {overview.activity.slice().reverse().map((event) => (
                <details key={event.event_id}>
                  <summary><span><Fingerprint size={15} aria-hidden="true" />{event.event_type}</span><code>#{event.sequence}</code></summary>
                  <dl>
                    <div><dt>Actor</dt><dd>{event.actor_id}</dd></div>
                    <div><dt>Trace</dt><dd>{event.trace_id}</dd></div>
                    <div><dt>Hash</dt><dd><code>{event.event_hash.slice(0, 20)}…</code></dd></div>
                  </dl>
                </details>
              ))}
            </section>
          </div>
          <details className="authority-matrix">
            <summary>Role boundaries and recovery rules</summary>
            <div>
              <p><strong>Facility worker</strong> records stock, requests approval, and submits signed receipts.</p>
              <p><strong>District Health Officer</strong> approves, issues notes, operates the worker, and acknowledges quarantined conflicts.</p>
              <p><strong>Auditor</strong> reads evidence only. Audit events redact secrets, raw images, prompts, and signed tokens.</p>
            </div>
          </details>
        </div>
      ) : null}
    </PageState>
  );
}
