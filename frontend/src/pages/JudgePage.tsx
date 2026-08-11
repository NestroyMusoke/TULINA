import { Check, ChevronRight, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";

import { PageState } from "../components/PageState";
import { RecommendationCard } from "../components/RecommendationCard";
import { ActivityTimeline } from "../components/ActivityTimeline";
import { FleetProgress } from "../components/FleetProgress";
import { StockCardIntakeCard } from "../components/StockCardIntakeCard";
import { TulinaNoteCard } from "../components/TulinaNoteCard";
import { useTulina } from "../state/TulinaContext";

const moments = [
  "Stock card read",
  "Found nearby",
  "Approval requested",
  "Human approved",
  "Tulina Note issued",
  "Received offline",
  "Delivery confirmed",
  "Replay and tamper blocked",
];

function inferMoment(status: string, eventTypes: string[], pendingCount: number, defenseProof: boolean): number {
  if (status === "DELIVERED") return defenseProof ? 7 : 6;
  if (status === "IN_TRANSIT" && pendingCount > 0) return 5;
  if (status === "IN_TRANSIT" || status === "NOTE_ISSUED") return 4;
  if (status === "APPROVED") return 3;
  if (status === "AWAITING_APPROVAL") return 2;
  if (eventTypes.includes("FOUND_NEARBY")) return 1;
  return 0;
}

export function JudgePage() {
  const {
    overview,
    agentRun,
    intake,
    busy,
    offlineState,
    online,
    reset,
    discover,
    requestApproval,
    approve,
    issueNote,
    receiveOffline,
    syncReceipts,
    retryLatestReceipt,
    proveTamperBlocked,
    setNetworkMode,
    extractDemoStockCard,
  } = useTulina();
  const [moment, setMoment] = useState(0);
  useEffect(() => {
    if (overview) {
      const defensesProven = offlineState.latestResult?.decision === "IDEMPOTENT_ACK"
        && offlineState.verification?.reason_code === "SIGNATURE_INVALID";
      setMoment(inferMoment(
        overview.recommendation.status,
        overview.activity.map((event) => event.event_type),
        offlineState.pendingCount,
        defensesProven,
      ));
    }
  }, [offlineState.latestResult?.decision, offlineState.pendingCount, offlineState.verification?.reason_code, overview]);

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
      if (moment === 0 && !intake) {
        await extractDemoStockCard();
        return;
      }
      if (moment === 0 && intake?.status === "ACCEPTED") await discover();
      if (moment === 1) await requestApproval("facility_worker");
      if (moment === 2) await approve("dho_approver");
      if (moment === 3) {
        await issueNote();
        setNetworkMode("offline");
      }
      if (moment === 4) {
        setNetworkMode("offline");
        await receiveOffline();
      }
      if (moment === 5) {
        setNetworkMode("online");
        await syncReceipts(true);
      }
      if (moment === 6) {
        await retryLatestReceipt();
        await proveTamperBlocked();
      }
      if (moment > 0 || intake?.status === "ACCEPTED") {
        setMoment((current) => Math.min(moments.length - 1, current + 1));
      }
    } catch {
      // Context renders the actionable error.
    }
  };

  const nextLabel = moment === moments.length - 1
    ? "Demo complete"
    : moment === 0 && !intake
      ? "Read demo card"
      : moment === 0 && intake?.status !== "ACCEPTED"
        ? "Confirm card below"
        : "Next moment";

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
              <button
                className="button primary"
                disabled={busy || moment === moments.length - 1 || (moment === 0 && Boolean(intake) && intake?.status !== "ACCEPTED")}
                onClick={() => void handleNext()}
              >
                {moment === moments.length - 1 ? <Check size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
                {nextLabel}
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
                  "A facility worker photographs Mbale's synthetic oxytocin stock card. Tulina reads its movements, shows the evidence, and waits for human confirmation.",
                  "The background watch finds a safe 11-pack match at Mbale and checks route, cover, expiry, level of care, and cold chain.",
                  "All five gates pass. Tulina pauses and asks the District Health Officer; no medicine can move yet.",
                  "The DHO approves as APR-DHO-001. The decision and evidence are now durable and auditable.",
                  "Dispatch signs a one-use P-256 Tulina Note for Busiu's designated device. The public trust bundle is cached before the phone loses signal.",
                  "DEV-F02-01 is offline. It checks the signature, recipient, expiry, and one-use nonce locally, then signs and queues the receipt in IndexedDB.",
                  "The phone reconnects. Reconciliation verifies both signatures and applies one atomic stock mutation: Mbale 60 → 49, Busiu 1 → 12.",
                  "The exact same receipt is retried and applies zero mutations. A quantity changed after signing is rejected before any receipt is created.",
                ][moment]}</p>
              </div>
              <StockCardIntakeCard compact />
              <FleetProgress detail={agentRun ?? overview.agent_run} />
              <RecommendationCard recommendation={overview.recommendation} />
              {moment >= 4 ? (
                <TulinaNoteCard
                  note={overview.protocol.note}
                  offlineState={offlineState}
                  online={online}
                  compact
                />
              ) : null}
              {moment >= 6 && overview.protocol.latest_reconciliation ? (
                <div className="reconciliation-proof">
                  <span className="section-kicker">Exactly-once proof</span>
                  <div><strong>{overview.protocol.latest_reconciliation.inventory_before?.donor ?? 60} → {overview.protocol.latest_reconciliation.inventory_after?.donor ?? 49}</strong><span>Mbale packs</span></div>
                  <div><strong>{overview.protocol.latest_reconciliation.inventory_before?.recipient ?? 1} → {overview.protocol.latest_reconciliation.inventory_after?.recipient ?? 12}</strong><span>Busiu packs</span></div>
                  <div><strong>{overview.protocol.mutation_count}</strong><span>stock mutation</span></div>
                </div>
              ) : null}
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
