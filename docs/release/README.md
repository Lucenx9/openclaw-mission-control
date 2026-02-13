# Release checklist (maintainers)

This project does not yet have a fully automated release pipeline.

Use this checklist for **manual releases** and as a place to evolve the process over time.

## Before you start

- [ ] You have maintainer permissions on `abhi1693/openclaw-mission-control`
- [ ] You know which **scope** you’re releasing:
  - [ ] backend-only change
  - [ ] frontend-only change
  - [ ] infra/docs-only change
  - [ ] full release

## 1) Pick the release commit

- [ ] Ensure you’re on the latest `master`:

```bash
git fetch origin
git checkout master
git reset --hard origin/master
```

- [ ] Identify the commit SHA you want to release (usually `origin/master`).

## 2) Verify CI + local checks

- [ ] CI is green on the target commit.
- [ ] Run the local CI-parity checks:

```bash
make setup
make check
make docs-check
```

## 3) Smoke test (recommended)

If the change affects runtime behavior (API/UI/auth), do a quick smoke test using the compose stack.

```bash
cp .env.example .env
# Configure .env (see repo README for auth mode notes)

docker compose -f compose.yml --env-file .env up -d --build

after_up() {
  echo "Frontend: http://localhost:3000"
  echo "Backend health: http://localhost:8000/healthz"
}

after_up
```

- [ ] Validate basic flows (at minimum):
  - [ ] frontend loads
  - [ ] backend `/healthz` returns 200
  - [ ] auth mode behaves as expected (local or clerk)

## 4) Prepare release notes

There is no enforced changelog format yet.

Choose one:
- [ ] GitHub Release notes (recommended for now)
- [ ] `CHANGELOG.md` (TODO: adopt Keep a Changelog)

Minimum release notes:
- [ ] Summary of key changes
- [ ] Any config changes / env var changes
- [ ] Any DB migration notes
- [ ] Known issues

## 5) Tag + publish

**TODO:** confirm the desired tag format (e.g. `v0.1.0`) and whether releases should be created from tags or from `master`.

Suggested manual flow:

```bash
# Example (adjust once tag conventions are decided)
git tag -a v0.0.0 -m "Release v0.0.0"
git push origin v0.0.0
```

- [ ] Create a GitHub Release from the tag
- [ ] Paste the release notes

## 6) Post-release

- [ ] Monitor new issues for regressions
- [ ] If you changed public behavior, ensure docs are updated (README + docs pages)

## Notes / follow-ups

- Consider adding:
  - automated versioning (changesets / semantic-release)
  - release workflow in `.github/workflows/release.yml`
  - a `CHANGELOG.md`
