import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api } from "../api";
import type { DemoRole, Overview } from "../types";

interface TulinaContextValue {
  overview: Overview | null;
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
      setOverview(await operation());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not complete that action");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);

  const reload = useCallback(() => run(api.overview), [run]);
  const reset = useCallback(() => run(api.reset), [run]);
  const discover = useCallback(() => run(api.discover), [run]);
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
    [overview, role, busy, error, online, reload, reset, discover, requestApproval, approve],
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
