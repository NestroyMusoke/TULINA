import { Check, Clock3, LoaderCircle, ShieldAlert } from "lucide-react";

import type { AgentRunDetail, AgentStepStatus } from "../types";

const fleet = [
  ["stock_intake_agent", "Stock intake"],
  ["watch_agent", "District watch"],
  ["match_agent", "Safe match"],
  ["steward_agent", "Policy steward"],
  ["dispatch_agent", "Dispatch gate"],
  ["reconciliation_agent", "Receipt gate"],
] as const;

function StepIcon({ status }: { status?: AgentStepStatus }) {
  if (status === "COMPLETED") return <Check size={14} aria-hidden="true" />;
  if (status === "RUNNING") return <LoaderCircle className="spin" size={14} aria-hidden="true" />;
  if (status === "FAILED") return <ShieldAlert size={14} aria-hidden="true" />;
  return <Clock3 size={14} aria-hidden="true" />;
}

export function FleetProgress({ detail }: { detail: AgentRunDetail | null }) {
  if (!detail) return null;
  const completed = detail.steps.filter((step) => ["COMPLETED", "WAITING"].includes(step.status)).length;
  const label = {
    QUEUED: "Queued",
    RUNNING: "Working quietly",
    COMPLETED: "Found nearby",
    FAILED: "Needs human review",
  }[detail.run.status];

  return (
    <section className={`fleet-progress ${detail.run.status.toLowerCase()}`} aria-live="polite">
      <div className="fleet-heading">
        <div><span className="section-kicker">Background work</span><h3>{label}</h3></div>
        <span>{completed} of {fleet.length} checks</span>
      </div>
      <div className="fleet-steps">
        {fleet.map(([name, humanLabel]) => {
          const step = detail.steps.find((item) => item.agent_name === name);
          return (
            <div className={`fleet-step ${step?.status.toLowerCase() ?? "pending"}`} key={name}>
              <span><StepIcon status={step?.status} /></span>
              <div><strong>{humanLabel}</strong><small>{step?.summary ?? "Waiting its turn"}</small></div>
            </div>
          );
        })}
      </div>
      <details className="fleet-proof">
        <summary>Technical proof</summary>
        <dl>
          <div><dt>Runtime</dt><dd>Google ADK · {detail.run.queue_backend}</dd></div>
          <div><dt>Run</dt><dd><code>{detail.run.run_id}</code></dd></div>
          <div><dt>Provider</dt><dd>{detail.run.provider === "gemini" ? detail.run.model_name : "Verified fixture mode"}</dd></div>
          <div><dt>ADK events</dt><dd>{detail.run.event_authors.length}</dd></div>
        </dl>
      </details>
    </section>
  );
}
