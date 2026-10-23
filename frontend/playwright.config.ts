// Playwright configuration for ALERT end-to-end tests.
//
// Strategy: run the real Vite dev server, then intercept every backend
// touchpoint (/api/**, /tiles) with page.route fixtures. This keeps E2E
// hermetic — no backend, ingest workers or external hazard feeds
// required — while still exercising the full React/map UI shell.

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3010',
    trace: 'retain-on-failure',
    // The app registers a real service worker (PWA offline); requests
    // re-issued from a controlled SW bypass page.route, which breaks
    // API mocking. Block SWs in tests — offline behaviour is not what
    // these specs exercise.
    serviceWorkers: 'block',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3010',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
