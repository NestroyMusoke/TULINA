import { AlertCircle, LoaderCircle, RotateCcw } from "lucide-react";

import { useTulina } from "../state/TulinaContext";

export function PageState({ children }: { children: React.ReactNode }) {
  const { overview, busy, error, reload } = useTulina();
  if (!overview && busy) {
    return (
      <div className="page-state" role="status">
        <LoaderCircle className="spin" aria-hidden="true" />
        <h1>Checking the district stock picture…</h1>
        <p>Tulina is loading validated synthetic demonstration data.</p>
      </div>
    );
  }
  if (!overview) {
    return (
      <div className="page-state error-state" role="alert">
        <AlertCircle aria-hidden="true" />
        <h1>We couldn’t reach the district service</h1>
        <p>{error ?? "Start the Tulina service, then try again."}</p>
        <button className="button primary" onClick={() => void reload().catch(() => undefined)}>
          <RotateCcw size={16} aria-hidden="true" /> Retry
        </button>
      </div>
    );
  }
  return (
    <>
      {error ? (
        <div className="inline-alert" role="alert">
          <AlertCircle size={17} aria-hidden="true" /> {error}
        </div>
      ) : null}
      {children}
    </>
  );
}
