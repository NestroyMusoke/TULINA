import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";
import { TulinaProvider } from "./state/TulinaContext";
import { agentRunFixture, overviewFixture } from "./test/fixture";

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

  test("judge next moment starts the real asynchronous ADK fleet", async () => {
    const discovered = {
      ...overviewFixture,
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
    let overviewCalls = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = String(input);
      if (url.includes("/api/v1/agent-runs/watch")) return response(agentRunFixture);
      if (url.includes("/api/v1/overview")) {
        overviewCalls += 1;
        return response(overviewCalls === 1 ? overviewFixture : discovered);
      }
      return response();
    });
    renderAt("/judge");
    const button = await screen.findByRole("button", { name: "Next moment" });
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("Moment 2 of 4")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/agent-runs/watch"),
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"product_id":"P05"') }),
    );
    expect(screen.getByText("6 of 6 checks")).toBeInTheDocument();
    expect(screen.getByText("Google ADK · local")).toBeInTheDocument();
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
});
