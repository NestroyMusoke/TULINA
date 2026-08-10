import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, waitForAgentRun } from "../api";
import type { AgentRunDetail, DemoRole, Overview } from "../types";

interface TulinaContextValue {
  overview: Overview | null;
  agentRun: AgentRunDetail | null;
  role: DemoRole;
  setRole: (role: DemoRole) => void;
  busy: boolean;
  error: string | null;
  online: boolean;
  reload: () => Promise<void>;
  reset: () => Promise<void>;
  discover: () => Promise<void>;
  requestApproval: (roleOverride?: DemoRole) => Promise<void>;
  approve: (roleOverride?: DemoRole) => Promise<void>;
}

const TulinaContext = createContext<TulinaContextValue | null>(null);

export function TulinaProvider({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunDetail | null>(null);
  const [role, setRole] = useState<DemoRole>("dho_approver");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const markOnline = () => setOnline(true);
    const markOffline = () => setOnline(false);
    window.addEventListener("online", markOnline);
    window.addEventListener("offline", markOffline);
    return () => {
      window.removeEventListener("online", markOnline);
      window.removeEventListener("offline", markOffline);
    };
  }, []);

  const run = useCallback(async (operation: () => Promise<Overview>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await operation();
      setOverview(next);
      setAgentRun(next.agent_run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not complete that action");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);

  const reload = useCallback(() => run(api.overview), [run]);
  const reset = useCallback(() => run(api.reset), [run]);
  const discover = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const started = await api.startWatchCycle();
      const completed = await waitForAgentRun(started, setAgentRun);
      setAgentRun(completed);
      setOverview(await api.overview());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not complete the background checks");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);
  const requestApproval = useCallback(
    (roleOverride?: DemoRole) => run(() => api.requestApproval(roleOverride ?? role)),
    [role, run],
  );
  const approve = useCallback(
    (roleOverride?: DemoRole) => run(() => api.approve(roleOverride ?? role)),
    [role, run],
  );

  useEffect(() => {
    void reload().catch(() => undefined);
  }, [reload]);

  const value = useMemo(
    () => ({
      overview,
      agentRun,
      role,
      setRole,
      busy,
      error,
      online,
      reload,
      reset,
      discover,
      requestApproval,
      approve,
    }),
    [overview, agentRun, role, busy, error, online, reload, reset, discover, requestApproval, approve],
  );
  return <TulinaContext.Provider value={value}>{children}</TulinaContext.Provider>;
}

// React Fast Refresh safely preserves this hook alongside its provider.
// eslint-disable-next-line react-refresh/only-export-components
export function useTulina() {
  const value = useContext(TulinaContext);
  if (!value) throw new Error("useTulina must be used inside TulinaProvider");
  return value;
}
