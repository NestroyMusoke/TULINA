import type { DemoRole, Overview } from "./types";

const API_URL = import.meta.env.VITE_API_URL?.replace(/\/$/, "") ?? "";

async function request(path: string, init?: RequestInit): Promise<Overview> {
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
  return (await response.json()) as Overview;
}

function roleHeaders(role: DemoRole): HeadersInit {
  return { "X-Tulina-Role": role };
}

export const api = {
  overview: () => request("/api/v1/overview"),
  reset: () => request("/api/v1/demo/reset", { method: "POST", headers: roleHeaders("dho_approver") }),
  discover: () => request("/api/v1/demo/discover", { method: "POST", headers: roleHeaders("facility_worker") }),
  requestApproval: (role: DemoRole = "facility_worker") =>
    request("/api/v1/transfers/TR-027/request-approval", { method: "POST", headers: roleHeaders(role) }),
  approve: (role: DemoRole = "dho_approver") =>
    request("/api/v1/transfers/TR-027/approve", { method: "POST", headers: roleHeaders(role) }),
};
