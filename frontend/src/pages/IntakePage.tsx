import { ShieldCheck } from "lucide-react";

import { PageState } from "../components/PageState";
import { StockCardIntakeCard } from "../components/StockCardIntakeCard";

export function IntakePage() {
  return (
    <PageState>
      <div className="page intake-page">
        <section className="page-title-row">
          <div>
            <span className="eyebrow">Facility stock intake</span>
            <h1>Read a stock card</h1>
            <p>Photograph the card, check every important field, then confirm the observation.</p>
          </div>
          <div className="chain-status"><ShieldCheck aria-hidden="true" /><strong>Human confirmation</strong><span>Required before district watch</span></div>
        </section>
        <StockCardIntakeCard />
        <p className="data-disclaimer">Synthetic demonstration card · no patient data · uploaded image bytes are not retained</p>
      </div>
    </PageState>
  );
}
