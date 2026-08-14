import type { AgentRunDetail, DemoRole, Overview, StockCardCorrection, StockCardIntake } from "./types";
import type { DeviceIdentity, ReconciliationResult, TrustBundle } from "./protocol/types";

const API_URL = import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const problem = (await response.json().catch(() => null)) as { detail?: string; request_id?: string } | null;
    const message = problem?.detail ?? `Tulina service returned ${response.status}`;
    throw new Error(problem?.request_id ? `${message} · Reference ${problem.request_id}` : message);
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
      body: JSON.stringify({ recipient_facility_id: "F02", product_id: "P05", trigger: "inventory_event" }),
    }),
  extractDemoStockCard: () =>
    request<StockCardIntake>("/api/v1/demo/stock-card-intakes", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
    }),
  uploadStockCard: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<StockCardIntake>("/api/v1/stock-card-intakes", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
      body,
    });
  },
  correctStockCard: (intakeId: string, correction: StockCardCorrection) =>
    request<StockCardIntake>(`/api/v1/stock-card-intakes/${intakeId}`, {
      method: "PATCH",
      headers: roleHeaders("facility_worker"),
      body: JSON.stringify(correction),
    }),
  acceptStockCard: (intakeId: string) =>
    request<StockCardIntake>(`/api/v1/stock-card-intakes/${intakeId}/accept`, {
      method: "POST",
      headers: roleHeaders("facility_worker"),
    }),
  agentRun: (runId: string) =>
    request<AgentRunDetail>(`/api/v1/agent-runs/${runId}`, { headers: roleHeaders("facility_worker") }),
  requestApproval: (role: DemoRole = "facility_worker") =>
    request<Overview>("/api/v1/transfers/TR-027/request-approval", { method: "POST", headers: roleHeaders(role) }),
  approve: (role: DemoRole = "dho_approver") =>
    request<Overview>("/api/v1/transfers/TR-027/approve", { method: "POST", headers: roleHeaders(role) }),
  trustBundle: () =>
    request<TrustBundle>("/api/v1/trust-bundle", { headers: roleHeaders("facility_worker") }),
  registerDevice: (identity: DeviceIdentity) =>
    request("/api/v1/devices/register", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
      body: JSON.stringify({
        schema_version: "1.0",
        device_id: identity.deviceId,
        facility_id: identity.facilityId,
        key_id: identity.keyId,
        public_jwk: identity.publicJwk,
      }),
    }),
  issueNote: () =>
    request<Overview>("/api/v1/transfers/TR-027/issue-note", { method: "POST", headers: roleHeaders("dho_approver") }),
  reconcileReceipt: (receiptToken: string) =>
    request<ReconciliationResult>("/api/v1/receipts/reconcile", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
      body: JSON.stringify({ receipt_token: receiptToken }),
    }),
  reportOfflineRejection: (report: {
    transfer_id: string;
    capsule_id: string;
    device_id: string;
    reason_code: string;
    occurred_at: string;
  }) =>
    request("/api/v1/security-events/offline-verification", {
      method: "POST",
      headers: roleHeaders("facility_worker"),
      body: JSON.stringify({ schema_version: "1.0", decision: "REJECT_OFFLINE", ...report }),
    }),
};

export const demoStockCardImageUrl = `${API_URL}/api/v1/demo/stock-card-image`;

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
