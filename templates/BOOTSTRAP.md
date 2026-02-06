# BOOTSTRAP.md - First Run

_This workspace may start without a human present. Do not wait for replies._

There is no memory yet. Create what is missing and proceed without blocking.

## Non‑interactive bootstrap (default)
1) Create `memory/` if missing.
2) Ensure `MEMORY.md` exists (create if missing).
3) Ensure either `SELF.md` exists (create if missing) or `MEMORY.md` contains an up-to-date `## SELF` section.
4) Read `IDENTITY.md`, `SOUL.md`, `SELF.md` (if present), and `USER.md`.
5) If any fields are blank, leave them blank. Do not invent values.
6) If `BASE_URL`, `AUTH_TOKEN`, and `BOARD_ID` are set in `TOOLS.md`, check in
   to Mission Control to mark the agent online:
```bash
curl -s -X POST "$BASE_URL/api/v1/agent/heartbeat" \
  -H "X-Agent-Token: $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "'$AGENT_NAME'", "board_id": "'$BOARD_ID'", "status": "online"}'
```
7) Write a short note to `MEMORY.md` that bootstrap completed and list any
   missing fields (e.g., user name, timezone).
8) Delete this file.

## Optional: if a human is already present
You may ask a short, single message to fill missing fields. If no reply arrives
quickly, continue with the non‑interactive bootstrap and do not ask again.

## After bootstrap
If you later receive user details, update `USER.md` and `IDENTITY.md` and note
the change in `MEMORY.md`.
