import type { IScannerControls } from "@zxing/browser";
import { Camera, Check, CloudUpload, FileImage, QrCode, ShieldAlert, ShieldCheck, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import type { OfflineState, SignedTulinaNote } from "../protocol/types";

interface Props {
  note: SignedTulinaNote | null;
  offlineState: OfflineState;
  online: boolean;
  busy?: boolean;
  compact?: boolean;
  onScan?: (token?: string) => Promise<void>;
  onSync?: () => Promise<void>;
}

export function TulinaNoteCard({ note, offlineState, online, busy, compact, onScan, onSync }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const controlsRef = useRef<IScannerControls | null>(null);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  useEffect(() => () => controlsRef.current?.stop(), []);

  const startCamera = async () => {
    if (!videoRef.current || !onScan) return;
    setCameraOpen(true);
    setScanError(null);
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      const reader = new BrowserQRCodeReader();
      controlsRef.current = await reader.decodeFromVideoDevice(undefined, videoRef.current, (result) => {
        if (!result) return;
        controlsRef.current?.stop();
        setCameraOpen(false);
        void onScan(result.getText());
      });
    } catch (reason) {
      setScanError(reason instanceof Error ? reason.message : "Camera scanning is unavailable");
      setCameraOpen(false);
    }
  };

  const scanFile = async (file: File | undefined) => {
    if (!file || !onScan) return;
    setScanError(null);
    const url = URL.createObjectURL(file);
    try {
      const { BrowserQRCodeReader } = await import("@zxing/browser");
      const result = await new BrowserQRCodeReader().decodeFromImageUrl(url);
      await onScan(result.getText());
    } catch {
      setScanError("No readable Tulina Note was found in that image");
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  if (!note) {
    return (
      <article className="note-card note-empty">
        <QrCode aria-hidden="true" />
        <div><span className="section-kicker">Tulina Note</span><h3>Waiting for DHO approval</h3><p>A signed receiving note appears only after a human approves the move.</p></div>
      </article>
    );
  }

  const queued = offlineState.pendingCount > 0;
  const confirmed = offlineState.latestResult?.decision === "APPLIED_EXACTLY_ONCE";
  const blocked = offlineState.verification?.decision === "REJECT_OFFLINE";
  return (
    <article className={`note-card ${compact ? "compact" : ""}`}>
      <div className="note-qr" aria-label="Scannable Tulina Note">
        <QRCodeSVG value={note.qr_payload} size={compact ? 132 : 184} level="M" marginSize={2} />
        <span>One use · signed</span>
      </div>
      <div className="note-copy">
        <span className="section-kicker">Tulina Note · {note.payload.capsule_id}</span>
        <h3>{confirmed ? "Delivery confirmed" : queued ? "Received offline" : "Safe authority to receive"}</h3>
        <p>{note.payload.qty} packs of oxytocin · Mbale to Busiu · approval {note.payload.approval}</p>
        <div className={`note-verification ${blocked ? "blocked" : confirmed ? "confirmed" : queued ? "queued" : "ready"}`} role="status">
          {blocked ? <ShieldAlert aria-hidden="true" /> : confirmed ? <Check aria-hidden="true" /> : queued ? <WifiOff aria-hidden="true" /> : <ShieldCheck aria-hidden="true" />}
          <span>
            <strong>{blocked ? offlineState.verification?.message : confirmed ? "Delivery confirmed" : queued ? "Received offline — checking in when connected" : "Signed for DEV-F02-01"}</strong>
            {!blocked && <small>{online ? "Trust bundle cached for offline use" : "Signature checked without internet"}</small>}
          </span>
        </div>
        {!compact && onScan ? (
          <div className="scanner-controls">
            <button className="button primary" disabled={busy || queued || confirmed} onClick={() => void onScan()}>
              <QrCode size={16} /> Check demo note
            </button>
            <button className="button ghost" disabled={busy || queued || confirmed} onClick={() => void startCamera()}>
              <Camera size={16} /> Use camera
            </button>
            <label className="button ghost file-scan">
              <FileImage size={16} /> Scan image
              <input type="file" accept="image/*" capture="environment" onChange={(event) => void scanFile(event.target.files?.[0])} />
            </label>
            {queued && online && onSync ? (
              <button className="button primary" disabled={busy} onClick={() => void onSync()}>
                <CloudUpload size={16} /> Check in now
              </button>
            ) : null}
          </div>
        ) : null}
        {cameraOpen ? <video className="qr-camera" ref={videoRef} muted playsInline aria-label="QR camera preview" /> : <video ref={videoRef} hidden muted playsInline />}
        {scanError ? <p className="inline-error" role="alert">{scanError}</p> : null}
        <details className="decision-details">
          <summary>How the note was checked</summary>
          <ul>
            <li>P-256 issuer signature: {offlineState.verification?.checks.signature ?? "ready"}</li>
            <li>Recipient binding: {offlineState.verification?.checks.recipient ?? "F02 / DEV-F02-01"}</li>
            <li>Expiry and one-use nonce: {offlineState.verification?.checks.nonce ?? "ready"}</li>
          </ul>
        </details>
      </div>
    </article>
  );
}
