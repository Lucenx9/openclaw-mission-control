# Testing guide

This repo’s CI parity entrypoint is:

```bash
make check
```

That target runs lint + typecheck + unit tests + coverage gate + frontend build.

## Quick commands

From repo root:

```bash
make setup

# Format + lint + typecheck + tests + build (CI parity)
make check
```

Docs-only quality gates:

```bash
make docs-check
```

## Backend

```bash
make backend-lint
make backend-typecheck
make backend-test
make backend-coverage
```

## Frontend

```bash
make frontend-lint
make frontend-typecheck
make frontend-test
make frontend-build
```

## E2E (Cypress)

CI runs Cypress E2E in `.github/workflows/ci.yml`.

Locally, the frontend package.json provides the E2E script:

```bash
cd frontend
npm run e2e
```

If your E2E tests require auth, ensure you have the necessary env configured (see root README for auth mode). Do **not** paste tokens into docs.
