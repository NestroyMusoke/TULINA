import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";
import { TulinaProvider } from "./state/TulinaContext";
import { agentRunFixture, overviewFixture, stockCardIntakeFixture } from "./test/fixture";

function response(payload: unknown = overviewFixture) {
  return Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }));
}

function renderAt(route: string) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <TulinaProvider>
        <App />
      </TulinaProvider>
    </MemoryRouter>,
  );
}

describe("Tulina judge experience", () => {
  test("explains the operational promise immediately", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response());
    renderAt("/district");
    expect(await screen.findByRole("heading", { name: /One clinic is empty/i })).toBeInTheDocument();
    expect(screen.getByText(/quietly finds safe medicine nearby/i)).toBeInTheDocument();
    expect(screen.getByText("Oxytocin 10 IU/ml")).toBeInTheDocument();
    expect(screen.getByText(/synthetic demonstration records.*not current facility data/i)).toBeInTheDocument();
  });

  test("judge path reads, confirms, then starts the asynchronous ADK fleet", async () => {
    const acceptedIntake = {
      ...stockCardIntakeFixture,
      status: "ACCEPTED" as const,
      accepted_by: "facility_worker",
      accepted_at: "2026-08-15T10:01:00Z",
    };
    const discovered = {
      ...overviewFixture,
      stock_card_intake: acceptedIntake,
      agent_run: agentRunFixture,
      activity: [
        ...overviewFixture.activity,
        {
          ...overviewFixture.activity[0],
          event_id: "EVT-002",
          sequence: 2,
          event_type: "FOUND_NEARBY",
          actor_id: "match_agent",
          summary: "Found safe oxytocin stock nearby for Busiu",
        },
      ],
    };
    let currentOverview = overviewFixture;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/demo/stock-card-intakes")) {
        currentOverview = { ...overviewFixture, stock_card_intake: stockCardIntakeFixture };
        return response(stockCardIntakeFixture);
      }
      if (url.includes("/accept")) {
        currentOverview = { ...overviewFixture, stock_card_intake: acceptedIntake };
        return response(acceptedIntake);
      }
      if (url.includes("/api/v1/agent-runs/watch")) {
        currentOverview = discovered;
        return response(agentRunFixture);
      }
      if (url.includes("/api/v1/overview")) return response(currentOverview);
      return response();
    });
    renderAt("/judge");
    fireEvent.click((await screen.findAllByRole("button", { name: "Read demo card" }))[0]);
    expect(await screen.findByRole("heading", { name: "Ready for human confirmation" })).toBeInTheDocument();
    expect(screen.getByText("60 packs")).toBeInTheDocument();
    expect(screen.getByText("Saved fixture extraction · Gemini was not called")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm stock observation" }));
    expect(await screen.findByText("Ready for district watch")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next moment" }));
    await waitFor(() => expect(screen.getByText("Moment 2 of 8")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/agent-runs/watch"),
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"trigger":"inventory_event"') }),
    );
    expect(screen.getByText("6 of 6 checks")).toBeInTheDocument();
    expect(screen.getByText("Google ADK · local")).toBeInTheDocument();
  });

  test("stock intake route exposes camera capture and review controls", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response());
    renderAt("/intake");
    expect(await screen.findByRole("heading", { name: "Read a stock card" })).toBeInTheDocument();
    const input = screen.getByLabelText("Take or upload photo");
    expect(input).toHaveAttribute("accept", "image/png,image/jpeg");
    expect(input).toHaveAttribute("capture", "environment");
  });

  test("facility route presents the receiving essentials", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response());
    renderAt("/facility");
    expect(await screen.findByRole("heading", { name: "Busiu receiving view" })).toBeInTheDocument();
    expect(screen.getByText("DEV-F02-01")).toBeInTheDocument();
    expect(screen.getByText("11 packs")).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, element) => element?.tagName === "SPAN" && element.textContent?.includes("5 days of cover") === true,
      ),
    ).toBeInTheDocument();
  });

  test("audit view reports server verification instead of assuming a valid chain", async () => {
    const failedAudit = {
      ...overviewFixture,
      governance: {
        ...overviewFixture.governance,
        audit_chain: { ...overviewFixture.governance.audit_chain, verified: false },
        unresolved_exceptions: 1,
      },
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(failedAudit));
    renderAt("/audit");
    expect(await screen.findByText("Chain needs review")).toBeInTheDocument();
    expect(screen.getByText("1 needs human review")).toBeInTheDocument();
    expect(screen.queryByText("Chain verified")).not.toBeInTheDocument();
  });
});
