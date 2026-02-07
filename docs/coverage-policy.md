# Coverage policy (CI gate)

## Why scoped coverage gates?

Today, overall repository coverage is low (especially for API routes and Next pages), but we still want CI to **enforce quality deterministically**.

So we start with a strict gate (100% statements + branches) on a **small, explicitly scoped** set of modules that are:

- unit-testable without external services
- stable and high-signal for regressions

We then expand the gated scope as we add tests.

## Backend scope (100% required)

Enforced in `Makefile` target `backend-coverage`:

- `app.core.error_handling`
- `app.services.mentions`

Command (CI):

```bash
cd backend && uv run pytest \
  --cov=app.core.error_handling \
  --cov=app.services.mentions \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml \
  --cov-report=json:coverage.json \
  --cov-fail-under=100
```

## Frontend scope (100% required)

Enforced in `frontend/vitest.config.ts` coverage settings:

- include: `src/lib/backoff.ts`
- thresholds: 100% for lines/statements/functions/branches

This is intentionally limited to a single pure utility module first. As we add more unit tests in `src/lib/**` and React Testing Library component tests for `src/app/**` + `src/components/**`, we should expand the include list and keep thresholds strict.

## How to expand the gate

- Add tests for the next-highest-signal modules.
- Add them to the gated scope (backend `--cov=` list; frontend `coverage.include`).
- Keep the threshold at 100% for anything included in the gate.
