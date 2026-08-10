import type { AgentRunDetail, DemoRole, Overview } from "./types";

const API_URL = import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(problem?.detail ?? `Tulina service returned ${response.status}`);
  }
  return (await response.json()) as T;
}

function roleHeaders(role: DemoRole): HeadersInit {
  return { "X-Tulina-Role": role };
}

export const api = {
  overview: () => request<Overview>("/api/v1/overview"),
  reset: () => request<Overview>("/api/v1/demo/reset", { method: "POST", headers: roleHeaders("dho_approver") }),
  startWatchCycle: () =>
    request<AgentRunDetail>("/api/v1/agent-runs/watch", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
      body: JSON.stringify({ recipient_facility_id: "F02", product_id: "P05", trigger: "demo" }),
    }),
  agentRun: (runId: string) =>
    request<AgentRunDetail>(`/api/v1/agent-runs/${runId}`, { headers: roleHeaders("facility_worker") }),
  requestApproval: (role: DemoRole = "facility_worker") =>
    request<Overview>("/api/v1/transfers/TR-027/request-approval", { method: "POST", headers: roleHeaders(role) }),
  approve: (role: DemoRole = "dho_approver") =>
    request<Overview>("/api/v1/transfers/TR-027/approve", { method: "POST", headers: roleHeaders(role) }),
};

export async function waitForAgentRun(
  initial: AgentRunDetail,
  onProgress: (detail: AgentRunDetail) => void,
): Promise<AgentRunDetail> {
  let detail = initial;
  onProgress(detail);
  for (let attempt = 0; attempt < 60 && ["QUEUED", "RUNNING"].includes(detail.run.status); attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 150));
    detail = await api.agentRun(detail.run.run_id);
    onProgress(detail);
  }
  if (detail.run.status === "FAILED") throw new Error("Background checks stopped — open the audit view for review");
  if (detail.run.status !== "COMPLETED") throw new Error("Background checks are taking longer than expected. Please retry.");
  return detail;
}
