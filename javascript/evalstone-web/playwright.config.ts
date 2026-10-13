import { defineConfig, devices } from "@playwright/test";

// The web app under test (a production build) and the API it talks to. Tests seed everything
// through the API (unique users per test), so any running center works — locally `just up`
// in python/evalstone-api on 8181; in CI the workflow starts one.
const PORT = process.env.PORT ?? "8192";
const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? `http://localhost:${PORT}`;
const apiURL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8181";

export default defineConfig({
  testDir: "./tests/specs",
  timeout: 60_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    trace: process.env.CI ? "retain-on-failure" : "on",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `NEXT_PUBLIC_API_URL=${apiURL} npm run build && NEXT_PUBLIC_API_URL=${apiURL} npx next start -p ${PORT}`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
