import {
  AlertTriangle,
  Camera,
  Check,
  FileCheck2,
  PencilLine,
  ScanLine,
  ThermometerSnowflake,
  Upload,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { demoStockCardImageUrl } from "../api";
import { useTulina } from "../state/TulinaContext";
import type { StockCardCorrection, StockCardExtraction } from "../types";

const fieldLabels: Record<string, string> = {
  facility_name: "Facility",
  product_name: "Medicine",
  on_hand_packs: "Current balance",
  batch_number: "Batch",
  expiry_date: "Expiry",
  storage_range: "Storage range",
  redistribution_review: "Redistribution remark",
  overall_confidence: "Whole card",
};

interface CorrectionForm {
  facility_name: string;
  product_name: string;
  on_hand_packs: string;
  batch_number: string;
  expiry_date: string;
  storage_min_c: string;
  storage_max_c: string;
  latest_temperature_c: string;
  redistribution_review: boolean;
}

function formFrom(extraction: StockCardExtraction): CorrectionForm {
  return {
    facility_name: extraction.facility_name,
    product_name: extraction.product_name,
    on_hand_packs: String(extraction.on_hand_packs),
    batch_number: extraction.batch_number,
    expiry_date: extraction.expiry_date,
    storage_min_c: String(extraction.storage_min_c),
    storage_max_c: String(extraction.storage_max_c),
    latest_temperature_c: String(extraction.latest_temperature_c),
    redistribution_review: extraction.redistribution_review,
  };
}

export function StockCardIntakeCard({ compact = false }: { compact?: boolean }) {
  const {
    intake,
    busy,
    extractDemoStockCard,
    uploadStockCard,
    correctStockCard,
    acceptStockCard,
  } = useTulina();
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [form, setForm] = useState<CorrectionForm | null>(null);

  useEffect(() => {
    if (intake) setForm(formFrom(intake.extraction));
  }, [intake]);

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    },
    [previewUrl],
  );

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(URL.createObjectURL(file));
    await uploadStockCard(file).catch(() => undefined);
  };

  const handleDemo = async () => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(null);
    await extractDemoStockCard().catch(() => undefined);
  };

  const handleCorrection = async (event: FormEvent) => {
    event.preventDefault();
    if (!intake || !form) return;
    const original = intake.extraction;
    const correction: StockCardCorrection = {};
    if (form.facility_name !== original.facility_name) correction.facility_name = form.facility_name;
    if (form.product_name !== original.product_name) correction.product_name = form.product_name;
    if (Number(form.on_hand_packs) !== original.on_hand_packs) correction.on_hand_packs = Number(form.on_hand_packs);
    if (form.batch_number !== original.batch_number) correction.batch_number = form.batch_number;
    if (form.expiry_date !== original.expiry_date) correction.expiry_date = form.expiry_date;
    if (Number(form.storage_min_c) !== original.storage_min_c) correction.storage_min_c = Number(form.storage_min_c);
    if (Number(form.storage_max_c) !== original.storage_max_c) correction.storage_max_c = Number(form.storage_max_c);
    if (Number(form.latest_temperature_c) !== original.latest_temperature_c) {
      correction.latest_temperature_c = Number(form.latest_temperature_c);
    }
    if (form.redistribution_review !== original.redistribution_review) {
      correction.redistribution_review = form.redistribution_review;
    }
    if (Object.keys(correction).length) await correctStockCard(correction).catch(() => undefined);
  };

  const imageUrl = previewUrl ?? demoStockCardImageUrl;
  if (!intake) {
    return (
      <section className={`stock-intake-card empty ${compact ? "compact" : ""}`}>
        <div className="stock-card-preview">
          <img src={imageUrl} alt="Supplied synthetic HMIS stock card for oxytocin" />
          <span><Camera size={14} aria-hidden="true" /> Supplied demo card</span>
        </div>
        <div className="stock-intake-empty-copy">
          <span className="section-kicker">Stock Intake Agent</span>
          <h3>Turn a stock card into checked data</h3>
          <p>Use the supplied synthetic card, or take a photo. Tulina shows what was read and asks a person to confirm it.</p>
          <div className="stock-intake-actions">
            <button className="button primary" disabled={busy} onClick={() => void handleDemo()}>
              <ScanLine size={16} aria-hidden="true" /> Read demo card
            </button>
            <label className="button ghost stock-upload-button">
              <Upload size={16} aria-hidden="true" /> Take or upload photo
              <input
                type="file"
                accept="image/png,image/jpeg"
                capture="environment"
                disabled={busy}
                onChange={(event) => void handleFile(event.target.files?.[0])}
              />
            </label>
          </div>
          <small>Fixture mode reads only this supplied card. Other images require Gemini mode.</small>
        </div>
      </section>
    );
  }

  const extraction = intake.extraction;
  const needsReview = intake.status === "NEEDS_REVIEW";
  const accepted = intake.status === "ACCEPTED";
  return (
    <section className={`stock-intake-card ${accepted ? "accepted" : needsReview ? "needs-review" : "ready"}`}>
      <div className="stock-card-preview">
        <img src={imageUrl} alt={`Uploaded stock card ${intake.source_filename}`} />
        <span><Camera size={14} aria-hidden="true" /> {intake.source_filename}</span>
      </div>
      <div className="stock-intake-result">
        <header>
          <div>
            <span className="section-kicker">Stock Intake Agent</span>
            <h3>{accepted ? "Stock observation confirmed" : needsReview ? "Check the highlighted fields" : "Ready for human confirmation"}</h3>
          </div>
          <div className={`intake-state ${accepted ? "accepted" : needsReview ? "review" : "ready"}`}>
            {accepted ? <Check size={15} /> : needsReview ? <AlertTriangle size={15} /> : <FileCheck2 size={15} />}
            {accepted ? "Accepted" : needsReview ? "Needs review" : "High confidence"}
          </div>
        </header>

        <div className="extracted-stock-grid">
          <div><span>Facility</span><strong>{extraction.facility_name}</strong><small>{intake.observation?.facility_id ?? "Identity to confirm"}</small></div>
          <div><span>Medicine</span><strong>{extraction.product_name}</strong><small>{intake.observation?.product_id ?? "Identity to confirm"}</small></div>
          <div className="balance"><span>Current balance</span><strong>{extraction.on_hand_packs} packs</strong><small>{extraction.stock_unit}</small></div>
          <div><span>Early batch</span><strong>{extraction.batch_number}</strong><small>Expires {extraction.expiry_date}</small></div>
          <div><span>Cold chain</span><strong>{extraction.storage_min_c}–{extraction.storage_max_c}°C</strong><small><ThermometerSnowflake size={12} /> Last entry {extraction.latest_temperature_c}°C</small></div>
          <div><span>Review flag</span><strong>{extraction.redistribution_review ? "Review for redistribution" : "No review noted"}</strong><small>{extraction.movements.length} movement rows read</small></div>
        </div>

        {intake.required_corrections.length ? (
          <div className="correction-warning" role="alert">
            <AlertTriangle size={16} aria-hidden="true" />
            <span><strong>Human correction required</strong>{intake.required_corrections.map((field) => fieldLabels[field] ?? field).join(", ")}</span>
          </div>
        ) : null}

        {intake.security_findings.length ? (
          <div className="security-finding" role="status">
            <AlertTriangle size={16} aria-hidden="true" />
            <span>
              <strong>Instruction-like text isolated</strong>
              Tulina kept the stock facts and isolated {intake.security_findings.length} unsafe instruction pattern{intake.security_findings.length === 1 ? "" : "s"}.
            </span>
          </div>
        ) : null}

        <details className="intake-evidence">
          <summary>Evidence and confidence · {Math.round(extraction.overall_confidence * 100)}%</summary>
          <ul>
            {extraction.evidence.map((evidence) => (
              <li key={evidence.field}>
                <span>{fieldLabels[evidence.field] ?? evidence.field}</span>
                <q>{evidence.quote}</q>
                <strong>{Math.round(evidence.confidence * 100)}%</strong>
              </li>
            ))}
          </ul>
          <p>{intake.gemini_called ? `${intake.model_name} · structured vision output` : "Saved fixture extraction · Gemini was not called"}</p>
        </details>

        {!accepted && form ? (
          <details className="intake-correction">
            <summary><PencilLine size={14} aria-hidden="true" /> Correct extracted fields</summary>
            <form onSubmit={(event) => void handleCorrection(event)}>
              <label>Facility<input value={form.facility_name} onChange={(event) => setForm({ ...form, facility_name: event.target.value })} /></label>
              <label>Medicine<input value={form.product_name} onChange={(event) => setForm({ ...form, product_name: event.target.value })} /></label>
              <label>Current packs<input type="number" min="0" value={form.on_hand_packs} onChange={(event) => setForm({ ...form, on_hand_packs: event.target.value })} /></label>
              <label>Batch<input value={form.batch_number} onChange={(event) => setForm({ ...form, batch_number: event.target.value })} /></label>
              <label>Expiry<input type="date" value={form.expiry_date} onChange={(event) => setForm({ ...form, expiry_date: event.target.value })} /></label>
              <label>Storage min °C<input type="number" step="0.1" value={form.storage_min_c} onChange={(event) => setForm({ ...form, storage_min_c: event.target.value })} /></label>
              <label>Storage max °C<input type="number" step="0.1" value={form.storage_max_c} onChange={(event) => setForm({ ...form, storage_max_c: event.target.value })} /></label>
              <label>Latest °C<input type="number" step="0.1" value={form.latest_temperature_c} onChange={(event) => setForm({ ...form, latest_temperature_c: event.target.value })} /></label>
              <label className="checkbox-field"><input type="checkbox" checked={form.redistribution_review} onChange={(event) => setForm({ ...form, redistribution_review: event.target.checked })} /> Review for redistribution</label>
              <button className="button ghost" disabled={busy} type="submit">Save correction</button>
            </form>
          </details>
        ) : null}

        <footer>
          <span>{intake.source_label}</span>
          {!accepted ? (
            <button className="button primary" disabled={busy || needsReview} onClick={() => void acceptStockCard().catch(() => undefined)}>
              <Check size={16} aria-hidden="true" /> Confirm stock observation
            </button>
          ) : <strong><Check size={15} /> Ready for district watch</strong>}
        </footer>
      </div>
    </section>
  );
}
