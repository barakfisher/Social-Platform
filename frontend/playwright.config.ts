import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 2,
  use: { baseURL: "http://127.0.0.1:53073" },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:53073",
    reuseExistingServer: !process.env.CI,
  },
  projects: [{ name: "chromium", use: { browserName: "chromium" } }],
});
