import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { api, waitForAgentRun } from "../api";
import { decodeNote, encodeEnvelope, verifyNoteOffline } from "../protocol/codec";
import {
  cacheTrustBundle,
  getCachedTrustBundle,
  getOrCreateDeviceIdentity,
  latestReceipt,
  pendingReceipts,
  resetOfflineState,
  updateReceipt,
  verifyAndQueueReceipt,
} from "../protocol/offlineStore";
import type { OfflineState, QueuedReceipt } from "../protocol/types";
import type { AgentRunDetail, DemoRole, Overview, StockCardCorrection, StockCardIntake } from "../types";

export type NetworkMode = "auto" | "online" | "offline";

interface TulinaContextValue {
  overview: Overview | null;
  agentRun: AgentRunDetail | null;
  intake: StockCardIntake | null;
  role: DemoRole;
  setRole: (role: DemoRole) => void;
  busy: boolean;
  error: string | null;
  online: boolean;
  networkMode: NetworkMode;
  setNetworkMode: (mode: NetworkMode) => void;
  offlineState: OfflineState;
  reload: () => Promise<void>;
  reset: () => Promise<void>;
  discover: () => Promise<void>;
  extractDemoStockCard: () => Promise<void>;
  uploadStockCard: (file: File) => Promise<void>;
  correctStockCard: (correction: StockCardCorrection) => Promise<void>;
  acceptStockCard: () => Promise<void>;
  requestApproval: (roleOverride?: DemoRole) => Promise<void>;
  approve: (roleOverride?: DemoRole) => Promise<void>;
  issueNote: () => Promise<void>;
  receiveOffline: (token?: string) => Promise<void>;
  syncReceipts: (force?: boolean) => Promise<void>;
  retryLatestReceipt: () => Promise<void>;
  proveTamperBlocked: () => Promise<void>;
}

const TulinaContext = createContext<TulinaContextValue | null>(null);

export function TulinaProvider({ children }: { children: React.ReactNode }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunDetail | null>(null);
  const [intake, setIntake] = useState<StockCardIntake | null>(null);
  const [role, setRole] = useState<DemoRole>("dho_approver");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [browserOnline, setBrowserOnline] = useState(() => navigator.onLine);
  const [networkMode, setNetworkMode] = useState<NetworkMode>("auto");
  const online = networkMode === "auto" ? browserOnline : networkMode === "online";
  const [offlineState, setOfflineState] = useState<OfflineState>({
    verification: null,
    pendingCount: 0,
    latestReceipt: null,
    latestResult: null,
  });

  useEffect(() => {
    const markOnline = () => setBrowserOnline(true);
    const markOffline = () => setBrowserOnline(false);
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
      setIntake(next.stock_card_intake);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not complete that action");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);

  const reload = useCallback(() => run(api.overview), [run]);
  const reset = useCallback(async () => {
    setNetworkMode("online");
    await resetOfflineState();
    setOfflineState({ verification: null, pendingCount: 0, latestReceipt: null, latestResult: null });
    await run(api.reset);
  }, [run]);
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
  const runIntake = useCallback(async (operation: () => Promise<StockCardIntake>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await operation();
      setIntake(next);
      const refreshed = await api.overview();
      setOverview(refreshed);
      setAgentRun(refreshed.agent_run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not read that stock card");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);
  const extractDemoStockCard = useCallback(() => runIntake(api.extractDemoStockCard), [runIntake]);
  const uploadStockCard = useCallback((file: File) => runIntake(() => api.uploadStockCard(file)), [runIntake]);
  const correctStockCard = useCallback(
    (correction: StockCardCorrection) => {
      if (!intake) return Promise.reject(new Error("Read a stock card before correcting it"));
      return runIntake(() => api.correctStockCard(intake.intake_id, correction));
    },
    [intake, runIntake],
  );
  const acceptStockCard = useCallback(() => {
    if (!intake) return Promise.reject(new Error("Read a stock card before confirming it"));
    return runIntake(() => api.acceptStockCard(intake.intake_id));
  }, [intake, runIntake]);
  const requestApproval = useCallback(
    (roleOverride?: DemoRole) => run(() => api.requestApproval(roleOverride ?? role)),
    [role, run],
  );
  const approve = useCallback(
    (roleOverride?: DemoRole) => run(() => api.approve(roleOverride ?? role)),
    [role, run],
  );

  const prepareDevice = useCallback(async () => {
    const bundle = await api.trustBundle();
    await cacheTrustBundle(bundle);
    const identity = await getOrCreateDeviceIdentity();
    await api.registerDevice(identity);
  }, []);

  const issueNote = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await prepareDevice();
      const next = await api.issueNote();
      setOverview(next);
      setAgentRun(next.agent_run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Tulina could not prepare the signed note");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, [prepareDevice]);

  const refreshOfflineState = useCallback(async (latest?: QueuedReceipt | null) => {
    const pending = await pendingReceipts();
    const receipt = latest === undefined ? await latestReceipt() : latest;
    setOfflineState((current) => ({
      ...current,
      pendingCount: pending.length,
      latestReceipt: receipt,
      latestResult: receipt?.result ?? current.latestResult,
    }));
  }, []);

  const receiveOffline = useCallback(async (token?: string) => {
    const noteToken = token ?? overview?.protocol.note?.qr_payload;
    if (!noteToken) throw new Error("Issue the Tulina Note before receiving medicine");
    setBusy(true);
    setError(null);
    try {
      const result = await verifyAndQueueReceipt(noteToken);
      setOfflineState((current) => ({
        ...current,
        verification: result.verification,
        latestReceipt: result.receipt ?? current.latestReceipt,
      }));
      await refreshOfflineState(result.receipt ?? undefined);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The note could not be checked offline");
      throw reason;
    } finally {
      setBusy(false);
    }
  }, [overview?.protocol.note?.qr_payload, refreshOfflineState]);

  const syncInFlight = useRef<Promise<void> | null>(null);
  const syncReceipts = useCallback((force = false): Promise<void> => {
    if (!online && !force) return Promise.resolve();
    if (syncInFlight.current) return syncInFlight.current;
    const operation = (async () => {
      setBusy(true);
      setError(null);
      try {
        const queued = await pendingReceipts();
        let newest: QueuedReceipt | null = null;
        for (const receipt of queued) {
          const result = await api.reconcileReceipt(receipt.receiptToken);
          newest = await updateReceipt(receipt, result);
        }
        if (newest) {
          setOfflineState((current) => ({ ...current, latestReceipt: newest, latestResult: newest?.result ?? null }));
        }
        await refreshOfflineState(newest ?? undefined);
        const refreshed = await api.overview();
        setOverview(refreshed);
        setAgentRun(refreshed.agent_run);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "Queued receipts could not check in");
        throw reason;
      } finally {
        setBusy(false);
      }
    })();
    syncInFlight.current = operation;
    void operation.then(
      () => { if (syncInFlight.current === operation) syncInFlight.current = null; },
      () => { if (syncInFlight.current === operation) syncInFlight.current = null; },
    );
    return operation;
  }, [online, refreshOfflineState]);

  const previousOnline = useRef(online);
  useEffect(() => {
    const reconnected = !previousOnline.current && online;
    previousOnline.current = online;
    if (reconnected) void syncReceipts().catch(() => undefined);
  }, [online, syncReceipts]);

  const retryLatestReceipt = useCallback(async () => {
    const receipt = offlineState.latestReceipt ?? await latestReceipt();
    if (!receipt) throw new Error("No receipt is available to retry");
    const result = await api.reconcileReceipt(receipt.receiptToken);
    const updated = await updateReceipt(receipt, result);
    setOfflineState((current) => ({ ...current, latestReceipt: updated, latestResult: result }));
    await reload();
  }, [offlineState.latestReceipt, reload]);

  const proveTamperBlocked = useCallback(async () => {
    const note = overview?.protocol.note;
    const bundle = await getCachedTrustBundle();
    if (!note || !bundle) throw new Error("Issue and cache a Tulina Note first");
    const decoded = decodeNote(note.qr_payload);
    const tamperedPayload = decoded.canonicalPayload.replace('"qty":11', '"qty":17');
    const tampered = encodeEnvelope("TULINA1", {
      key_id: decoded.keyId,
      canonical_payload: tamperedPayload,
      signature_base64url: decoded.signature,
    });
    const verification = await verifyNoteOffline({
      token: tampered,
      trustBundle: bundle,
      facilityId: "F02",
    });
    setOfflineState((current) => ({ ...current, verification }));
    if (verification.decision === "REJECT_OFFLINE" && online) {
      await api.reportOfflineRejection({
        transfer_id: decoded.payload.transfer_id,
        capsule_id: decoded.payload.capsule_id,
        device_id: "DEV-F02-01",
        reason_code: verification.reason_code,
        occurred_at: new Date().toISOString(),
      });
      await reload();
    }
  }, [online, overview?.protocol.note, reload]);

  useEffect(() => {
    void reload().catch(() => undefined);
  }, [reload]);

  const value = useMemo(
    () => ({
      overview,
      agentRun,
      intake,
      role,
      setRole,
      busy,
      error,
      online,
      networkMode,
      setNetworkMode,
      offlineState,
      reload,
      reset,
      discover,
      extractDemoStockCard,
      uploadStockCard,
      correctStockCard,
      acceptStockCard,
      requestApproval,
      approve,
      issueNote,
      receiveOffline,
      syncReceipts,
      retryLatestReceipt,
      proveTamperBlocked,
    }),
    [
      overview,
      agentRun,
      intake,
      role,
      busy,
      error,
      online,
      networkMode,
      offlineState,
      reload,
      reset,
      discover,
      extractDemoStockCard,
      uploadStockCard,
      correctStockCard,
      acceptStockCard,
      requestApproval,
      approve,
      issueNote,
      receiveOffline,
      syncReceipts,
      retryLatestReceipt,
      proveTamperBlocked,
    ],
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
