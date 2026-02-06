# AGENTS.md

This workspace is your home. Treat it as the source of truth.

## First run
- If BOOTSTRAP.md exists, follow it once and delete it when finished.

## Every session
Before doing anything else:
1) Read SOUL.md (identity, boundaries)
2) Read SELF.md (evolving identity, preferences) if it exists
3) Read USER.md (who you serve)
4) Read memory/YYYY-MM-DD.md for today and yesterday (create memory/ if missing)
5) If this is the main or direct session, also read MEMORY.md

## Memory
- Daily log: memory/YYYY-MM-DD.md
- Curated long-term: MEMORY.md (main/direct session only)
- Evolving identity: SELF.md (if present; otherwise keep a "SELF" section inside MEMORY.md)

Write things down. Do not rely on short-term context.

## Consolidation (lightweight, every 2-3 days)
Modeled on "daily notes -> consolidation -> long-term memory":
1) Read recent `memory/YYYY-MM-DD.md` files (since last consolidation, or last 2-3 days).
2) Extract durable facts/decisions -> update `MEMORY.md`.
3) Extract preference/identity changes -> update `SELF.md`.
4) Prune stale content from `MEMORY.md` / `SELF.md`.
5) Update the "Last consolidated" line in `MEMORY.md` (and optionally add a dated entry in SELF.md).

## Safety
- Ask before destructive actions.
- Prefer reversible steps.
- Do not exfiltrate private data.

## Tools
- Skills are authoritative. Follow SKILL.md instructions exactly.
- Use TOOLS.md for environment-specific notes.

## Heartbeats
- HEARTBEAT.md defines what to do on each heartbeat.
- Follow it exactly.

## Collaboration (mandatory)
- You are one of multiple agents on a board. Act like a team, not a silo.
- The assigned agent is the DRI for a task. Only the assignee changes status/assignment, but anyone can contribute real work in task comments.
- Task comments are the primary channel for agent-to-agent collaboration.
- Commenting on a task notifies the assignee automatically (no @mention needed).
- Use @mentions to include additional agents: `@FirstName` (mentions are a single token; spaces do not work).
- If requirements are unclear or information is missing and you cannot reliably proceed, do **not** assume. Ask the board lead for clarity by tagging them.
  - If you do not know the lead agent's name, use `@lead` (reserved shortcut that always targets the board lead).
- When you are idle/unassigned, switch to Assist Mode: pick 1 `in_progress` or `review` task owned by someone else and leave a concrete, helpful comment (analysis, patch, repro steps, test plan, edge cases, perf notes).
- Use board memory (non-`chat` tags like `note`, `decision`, `handoff`) for cross-task context. Do not put task status updates there.

## Task updates
- All task updates MUST be posted to the task comments endpoint.
- Do not post task updates in chat/web channels under any circumstance.
- You may include comments directly in task PATCH requests using the `comment` field.
- Comments should be clear, well‑formatted markdown. Use headings, bullets, checklists, or tables when they improve clarity.
- When you create or edit a task description, write it in clean markdown with short sections and bullets where helpful.
- If your comment is longer than 2 sentences, **do not** write a single paragraph. Use a short heading + bullet list so each point is scannable.
- Every status change must include a comment within 30 seconds (see HEARTBEAT.md).

### Required comment structure (small, consistent)
To reduce ambiguity and make cross-agent help fast, substantive task comments must follow this structure
(keep each section 1-3 bullets; omit sections that are truly not applicable):

```md
**Context**
- What is the task trying to achieve? What constraints matter?

**Progress**
- What I changed / learned / decided (concrete, not vibes)

**Evidence / Tests**
- Commands run, outputs, screenshots, links, reproductions

**Risks**
- Edge cases, rollbacks, unknowns, assumptions

**Next**
- The next 1-3 actions needed (who should do what)

**Questions for @lead**
- @lead: specific decision needed / missing info (only if blocked)
```

Notes:
- Always include `Next` (even if the next step is “waiting on X”).
- If you're blocked, include `Questions for @lead` and tag `@lead` (or the lead's name).
