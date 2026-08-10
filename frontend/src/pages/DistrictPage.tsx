import { Activity, CalendarClock, PackageCheck, Radio, ShieldCheck, TimerReset } from "lucide-react";

import { ActivityTimeline } from "../components/ActivityTimeline";
import { PageState } from "../components/PageState";
import { RecommendationCard } from "../components/RecommendationCard";
import { useTulina } from "../state/TulinaContext";

export function DistrictPage() {
  const { overview } = useTulina();
  return (
    <PageState>
      {overview ? (
        <div className="page district-page">
          <section className="hero-grid">
            <div className="hero-copy">
              <span className="eyebrow">Mbale district · synthetic demonstration</span>
              <h1>One clinic is empty.<br /><em>The district isn’t.</em></h1>
              <p>Tulina quietly finds safe medicine nearby, checks the rules, and brings the right human in before anything moves.</p>
              <div className="watch-line">
                <Radio size={17} aria-hidden="true" />
                <span><strong>Watching in the background</strong> · 70 stock positions checked</span>
              </div>
            </div>
            <aside className="district-stamp" aria-label="District picture date">
              <span>District picture</span>
              <strong>15 Aug</strong>
              <small>Verified fixture</small>
            </aside>
          </section>

          <div className="content-grid">
            <RecommendationCard recommendation={overview.recommendation} />
            <aside className="impact-column">
              <div className="section-heading">
                <span className="section-kicker">If approved</span>
                <h2>What improves</h2>
              </div>
              <div className="impact-cards">
                <article>
                  <TimerReset aria-hidden="true" />
                  <span>Busiu cover</span>
                  <strong>5 → 60 days</strong>
                  <small>Restores a two-month working buffer</small>
                </article>
                <article>
                  <PackageCheck aria-hidden="true" />
                  <span>Expiry risk</span>
                  <strong>11 packs used</strong>
                  <small>From the earliest-expiry safe batch</small>
                </article>
                <article>
                  <CalendarClock aria-hidden="true" />
                  <span>Donor protected</span>
                  <strong>122 days left</strong>
                  <small>Well above the 30-day safety floor</small>
                </article>
              </div>
              <div className="assurance-note">
                <ShieldCheck size={18} aria-hidden="true" />
                <p><strong>Human authority stays in place.</strong> Tulina can find and prepare this move. Only the DHO can approve it.</p>
              </div>
            </aside>
          </div>

          <section className="activity-section">
            <div className="section-heading row-heading">
              <div>
                <span className="section-kicker">Quiet background work</span>
                <h2>Activity</h2>
              </div>
              <Activity size={20} aria-hidden="true" />
            </div>
            <ActivityTimeline events={overview.activity} />
          </section>
          <p className="data-disclaimer">All stock, consumption, transfer, and device values shown are synthetic demonstration records—not current facility data. No patient data is used.</p>
        </div>
      ) : null}
    </PageState>
  );
}
