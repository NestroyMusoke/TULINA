import { Check, Clock3, Database, Search, ShieldCheck } from "lucide-react";

import type { ActivityEvent } from "../types";

function eventIcon(type: string) {
  if (type === "FOUND_NEARBY") return Search;
  if (type.includes("APPROVED")) return Check;
  if (type.includes("AWAITING")) return Clock3;
  if (type.includes("SEEDED") || type === "DEMO_RESET") return Database;
  return ShieldCheck;
}

function eventLabel(event: ActivityEvent): string {
  const labels: Record<string, string> = {
    FIXTURE_SEEDED: "Stock picture ready",
    DEMO_RESET: "Demo reset",
    AGENT_RUN_QUEUED: "Background check queued",
    AGENT_RUN_STARTED: "Background check started",
    STOCK_INTAKE_READY: "Stock picture validated",
    WATCH_SIGNALS_CREATED: "District stock checked",
    FOUND_NEARBY: "Found nearby",
    STEWARDSHIP_REVIEW_COMPLETED: "Safety review complete",
    DISPATCH_WAITING_FOR_APPROVAL: "Waiting for human approval",
    RECONCILIATION_WAITING_FOR_RECEIPT: "Receipt gate standing by",
    AGENT_RUN_COMPLETED: "Background check complete",
    STOCK_CARD_EXTRACTED: "Stock card read",
    STOCK_CARD_CORRECTED: "Stock card corrected",
    STOCK_CARD_ACCEPTED: "Stock observation confirmed",
    AGENT_RUN_FAILED: "Needs human review",
    TRANSFER_AWAITING_APPROVAL: "Sent for approval",
    TRANSFER_APPROVED: "Human approval recorded",
    TRANSFER_NOTE_ISSUED: "Tulina Note issued",
    TRANSFER_IN_TRANSIT: "Ready for offline receiving",
    RECIPIENT_DEVICE_READY: "Receiving phone ready",
    ADK_DISPATCH_COMPLETED: "Dispatch Agent signed the note",
    TRANSFER_DELIVERED: "Delivery confirmed",
    ADK_RECONCILIATION_COMPLETED: "Reconciliation Agent checked receipt",
    DUPLICATE_RECEIPT_RETRY: "Duplicate applied zero",
    RECEIPT_REJECTED: "Unsafe receipt rejected",
    RECEIPT_QUARANTINED: "Needs human review",
  };
  return labels[event.event_type] ?? event.event_type.toLowerCase().replaceAll("_", " ");
}

export function ActivityTimeline({ events, limit = 6 }: { events: ActivityEvent[]; limit?: number }) {
  const visible = events.slice(-limit).reverse();
  return (
    <div className="timeline">
      {visible.map((event) => {
        const Icon = eventIcon(event.event_type);
        return (
          <article key={event.event_id} className="timeline-item">
            <div className="timeline-icon">
              <Icon size={16} aria-hidden="true" />
            </div>
            <div>
              <div className="timeline-heading">
                <strong>{eventLabel(event)}</strong>
                <time dateTime={event.occurred_at}>
                  {new Date(event.occurred_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                </time>
              </div>
              <p>{event.summary}</p>
              <span>{event.actor_id}</span>
            </div>
          </article>
        );
      })}
    </div>
  );
}
