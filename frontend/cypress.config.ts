import { defineConfig } from "cypress";

export default defineConfig({
  e2e: {
    baseUrl: "http://localhost:3000",
    video: false,
    screenshotOnRunFailure: true,
    specPattern: "cypress/e2e/**/*.cy.{ts,tsx,js,jsx}",
    supportFile: "cypress/support/e2e.ts",
  },
});
