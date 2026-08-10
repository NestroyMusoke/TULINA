import { Check, ChevronRight, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { PageState } from "../components/PageState";
import { RecommendationCard } from "../components/RecommendationCard";
import { ActivityTimeline } from "../components/ActivityTimeline";
import { useTulina } from "../state/TulinaContext";

const moments = ["District picture", "Found nearby", "Approval requested", "Human approved"];

function inferMoment(status: string, eventTypes: string[]): number {
  if (status === "APPROVED") return 3;
  if (status === "AWAITING_APPROVAL") return 2;
  if (eventTypes.includes("FOUND_NEARBY")) return 1;
  return 0;
}

export function JudgePage() {
  const { overview, busy, reset, discover, requestApproval, approve } = useTulina();
  const [moment, setMoment] = useState(0);
  useEffect(() => {
    if (overview) setMoment(inferMoment(overview.recommendation.status, overview.activity.map((event) => event.event_type)));
  }, [overview]);

  const handleReset = async () => {
    try {
      await reset();
      setMoment(0);
    } catch {
      // Context renders the actionable error.
    }
  };

  const handleNext = async () => {
    try {
      if (moment === 0) await discover();
      if (moment === 1) await requestApproval("facility_worker");
      if (moment === 2) await approve("dho_approver");
      setMoment((current) => Math.min(3, current + 1));
    } catch {
      // Context renders the actionable error.
    }
  };

  return (
    <PageState>
      {overview ? (
        <div className="page judge-page">
          <section className="demo-controller">
            <div>
              <span className="eyebrow">Four-minute judge path</span>
              <h1>See Tulina take action</h1>
              <p>Every moment below runs the real stock, policy, workflow, and audit logic.</p>
            </div>
            <div className="demo-actions">
              <button className="button ghost" disabled={busy} onClick={() => void handleReset()}>
                <RotateCcw size={16} aria-hidden="true" /> Reset demo
              </button>
              <button className="button primary" disabled={busy || moment === 3} onClick={() => void handleNext()}>
                {moment === 3 ? <Check size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                {moment === 3 ? "Approval complete" : "Next moment"}
              </button>
            </div>
          </section>

          <ol className="moment-track" aria-label="Demo progress">
            {moments.map((label, index) => (
              <li key={label} className={index < moment ? "complete" : index === moment ? "current" : ""}>
                <span>{index < moment ? <Check size={13} aria-hidden="true" /> : index + 1}</span>
                <strong>{label}</strong>
              </li>
            ))}
          </ol>

          <div className="judge-story-grid">
            <div>
              <div className="story-intro">
                <span className="eyebrow">Moment {moment + 1} of {moments.length}</span>
                <h2>{moments[moment]}</h2>
                <p>{[
                  "Busiu has one pack of oxytocin—about five days of cover. Tulina is watching the whole district.",
                  "The background watch finds a safe 11-pack match at Mbale and checks route, cover, expiry, level of care, and cold chain.",
                  "All five gates pass. Tulina pauses and asks the District Health Officer; no medicine can move yet.",
                  "The DHO approves as APR-DHO-001. The decision and evidence are now durable and auditable.",
                ][moment]}</p>
              </div>
              <RecommendationCard recommendation={overview.recommendation} />
            </div>
            <aside className="judge-activity">
              <div className="section-heading">
                <span className="section-kicker">Live proof</span>
                <h2>What just happened</h2>
              </div>
              <ActivityTimeline events={overview.activity} limit={8} />
              <div className="proof-footer">
                <span>Persistent state</span>
                <span>Human authority</span>
                <span>Hash-chained audit</span>
              </div>
            </aside>
          </div>
        </div>
      ) : null}
    </PageState>
  );
}
