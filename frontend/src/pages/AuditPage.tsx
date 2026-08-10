import { Fingerprint, ShieldCheck } from "lucide-react";

import { ActivityTimeline } from "../components/ActivityTimeline";
import { FleetProgress } from "../components/FleetProgress";
import { PageState } from "../components/PageState";
import { useTulina } from "../state/TulinaContext";

export function AuditPage() {
  const { overview } = useTulina();
  return (
    <PageState>
      {overview ? (
        <div className="page audit-page">
          <section className="page-title-row"><div><span className="eyebrow">Audit view</span><h1>Every decision leaves a record</h1><p>Concise operational evidence and tool events—never hidden model reasoning.</p></div><div className="chain-status"><ShieldCheck aria-hidden="true" /><strong>Chain verified</strong><span>SHA-256 linked events</span></div></section>
          <FleetProgress detail={overview.agent_run} />
          <div className="audit-grid"><section className="activity-section"><div className="section-heading"><span className="section-kicker">Human-readable</span><h2>Activity timeline</h2></div><ActivityTimeline events={overview.activity} limit={20} /></section><section className="audit-records"><div className="section-heading"><span className="section-kicker">Technical proof</span><h2>Event records</h2></div>{overview.activity.slice().reverse().map((event) => <details key={event.event_id}><summary><span><Fingerprint size={15} aria-hidden="true" />{event.event_type}</span><code>#{event.sequence}</code></summary><dl><div><dt>Actor</dt><dd>{event.actor_id}</dd></div><div><dt>Trace</dt><dd>{event.trace_id}</dd></div><div><dt>Hash</dt><dd><code>{event.event_hash.slice(0, 20)}…</code></dd></div></dl></details>)}</section></div>
        </div>
      ) : null}
    </PageState>
  );
}
