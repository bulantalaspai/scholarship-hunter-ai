import { defineConfig, devices } from '@playwright/test'
import { fileURLToPath } from 'node:url'

const repositoryRoot = fileURLToPath(new URL('..', import.meta.url))
const python = fileURLToPath(
  new URL(
    process.platform === 'win32'
      ? '../.venv/Scripts/python.exe'
      : '../.venv/bin/python',
    import.meta.url,
  ),
)

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  workers: 2,
  use: { baseURL: 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `"${python}" -m frontend.e2e.start_test_api`,
      cwd: repositoryRoot,
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
