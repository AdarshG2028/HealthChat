import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the REAL backend running with MOCK providers:
 * zero LLM / Jev calls, zero credits. Both servers are started automatically.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // The dev server compiles each route on first hit, which can take a while on a cold start.
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: { baseURL: "http://localhost:3100", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: "uv run alembic upgrade head && uv run uvicorn app.main:create_app --factory --port 8000",
      cwd: "../backend",
      url: "http://localhost:8000/healthz",
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: "sqlite+aiosqlite:///./e2e.db",
        LLM_PROVIDER: "mock",
        JEV_PROVIDER: "mock",
        OTEL_ENABLED: "false",
        CORS_ORIGINS: '["http://localhost:3100"]',
      },
    },
    {
      command: "pnpm dev",
      url: "http://localhost:3100",
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_URL: "http://localhost:8000" },
    },
  ],
});
