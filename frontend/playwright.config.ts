import { defineConfig, devices } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(frontendRoot, "..");
const python = process.env.TULINA_E2E_PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const quotedPython = `"${python.replaceAll('"', '\\"')}"`;
const browserChannel = process.env.TULINA_E2E_BROWSER_CHANNEL;

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "line",
  expect: { timeout: 10_000 },
  timeout: 60_000,
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], ...(browserChannel ? { channel: browserChannel } : {}) },
    },
  ],
  webServer: [
    {
      command: `${quotedPython} -m uvicorn backend.tulina.api:app --host 127.0.0.1 --port 8080`,
      cwd: repositoryRoot,
      url: "http://127.0.0.1:8080/readyz",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        TULINA_MODE: "fixture",
        TULINA_QUEUE: "local",
        TULINA_AGENT_STEP_DELAY_MS: "0",
        TULINA_DATABASE_PATH: path.join(repositoryRoot, "work", "e2e.sqlite3"),
      },
    },
    {
      command: "npm run dev -- --host 127.0.0.1 --port 5173",
      cwd: frontendRoot,
      url: "http://127.0.0.1:5173/judge",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
