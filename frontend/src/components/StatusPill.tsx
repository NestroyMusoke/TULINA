import { Check, Clock3, MapPin, ShieldAlert, Sparkles } from "lucide-react";

import type { TransferStatus } from "../types";

const labels: Record<TransferStatus, string> = {
  FOUND: "Found nearby",
  AWAITING_APPROVAL: "Waiting for DHO",
  APPROVED: "Approved",
  NOTE_ISSUED: "Tulina Note ready",
  IN_TRANSIT: "On the way",
  DELIVERED: "Delivery confirmed",
  NEEDS_REVIEW: "Needs human review",
  CANCELLED: "Cancelled",
};

export function StatusPill({ status }: { status: TransferStatus }) {
  const Icon =
    status === "FOUND"
      ? Sparkles
      : status === "AWAITING_APPROVAL"
        ? Clock3
        : status === "DELIVERED" || status === "APPROVED"
          ? Check
          : status === "NEEDS_REVIEW" || status === "CANCELLED"
            ? ShieldAlert
            : MapPin;
  return (
    <span className={`status-pill status-${status.toLowerCase()}`}>
      <Icon size={14} aria-hidden="true" /> {labels[status]}
    </span>
  );
}
