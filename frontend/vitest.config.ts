import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/setupTests.ts"],
    globals: true,
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "./coverage",
      // Policy (scoped gate): require 100% coverage on *explicitly listed* unit-testable modules first.
      // We'll expand this include list as we add more unit/component tests.
      include: ["src/lib/backoff.ts"],
      exclude: ["**/*.d.ts", "src/**/__generated__/**", "src/**/generated/**"],
      thresholds: {
        lines: 100,
        statements: 100,
        functions: 100,
        branches: 100,
      },
    },
  },
});
