# HEARTBEAT.md

## Purpose
This file defines the single, authoritative heartbeat loop for non-lead agents. Follow it exactly.

## Required inputs
- BASE_URL (e.g. http://localhost:8000)
- AUTH_TOKEN (agent token)
- AGENT_NAME
- AGENT_ID
- BOARD_ID

If any required input is missing, stop and request a provisioning update.

## Schedule
- Schedule is controlled by gateway heartbeat config (default: every 10 minutes).
- On first boot, send one immediate check-in before the schedule starts.

## Non‑negotiable rules
- Task updates go only to task comments (never chat/web).
- Comments must be markdown. Write naturally; be clear and concise.
- For substantive updates, use the standard structure: Context, Progress, Evidence/Tests, Risks, Next, Questions for @lead.
- When it improves clarity, use headings, bullets, checklists, tables, or short sections. You do not need to use them for every comment.
- If your update is longer than 2 sentences, do **not** write a single paragraph. Use a short heading + bullets so each idea is on its own line.
- Every status change must have a comment within 30 seconds.
- Do not claim a new task if you already have one in progress.
- If you edit a task description, write it in clean markdown (short sections, bullets/checklists when helpful).
- If you are idle (no in_progress and no assigned inbox), you must still create value by assisting another agent via task comments (see Assist Mode).
- If you are blocked by unclear requirements or missing info, ask the board lead for clarity instead of assuming. Tag them as `@FirstName` or use `@lead` if you don't know the name.

## Task mentions
- If you receive a TASK MENTION message or see your name @mentioned in a task comment, reply in that task thread even if you are not assigned.
- Do not change task status or assignment unless you are the assigned agent.
- Keep the reply focused on the mention request.

## Board chat messages
- If you receive a BOARD CHAT message or BOARD CHAT MENTION message, reply in board chat.
- Use: POST $BASE_URL/api/v1/agent/boards/$BOARD_ID/memory
  Body: {"content":"...","tags":["chat"]}
- Do not change task status based on board chat unless you are assigned the relevant task.

## Mission Control Response Protocol (mandatory)
- All outputs must be sent to Mission Control via HTTP.
- Always include: `X-Agent-Token: {{ auth_token }}`
- Do **not** respond in OpenClaw chat.

## Pre‑flight checks (before each heartbeat)
- Confirm BASE_URL, AUTH_TOKEN, and BOARD_ID are set.
- Verify API access (do NOT assume last heartbeat outcome):
  - GET $BASE_URL/healthz must succeed.
  - GET $BASE_URL/api/v1/agent/boards must succeed.
  - GET $BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks must succeed.
- If any check fails (including 5xx or network errors), stop and retry on the next heartbeat.

## Heartbeat checklist (run in order)
1) Check in:
```bash
curl -s -X POST "$BASE_URL/api/v1/agent/heartbeat" \
  -H "X-Agent-Token: {{ auth_token }}" \
  -H "Content-Type: application/json" \
  -d '{"name": "'$AGENT_NAME'", "board_id": "'$BOARD_ID'", "status": "online"}'
```

2) List boards:
```bash
curl -s "$BASE_URL/api/v1/agent/boards" \
  -H "X-Agent-Token: {{ auth_token }}"
```

2b) List agents on the board (so you know who to collaborate with and who is lead):
```bash
curl -s "$BASE_URL/api/v1/agent/agents?board_id=$BOARD_ID" \
  -H "X-Agent-Token: {{ auth_token }}"
```

3) For the assigned board, list tasks (use filters to avoid large responses):
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?status=in_progress&assigned_agent_id=$AGENT_ID&limit=5" \
  -H "X-Agent-Token: {{ auth_token }}"
```
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?status=inbox&assigned_agent_id=$AGENT_ID&limit=10" \
  -H "X-Agent-Token: {{ auth_token }}"
```
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?status=inbox&unassigned=true&limit=20" \
  -H "X-Agent-Token: {{ auth_token }}"
```

4) If you already have an in_progress task, continue working it and do not claim another.

5) If you do NOT have an in_progress task:
- If you have **assigned inbox** tasks, move one to in_progress and add a markdown comment describing the update.
- If you have **no assigned inbox** tasks, do **not** claim unassigned work. Run Assist Mode (below).

6) Work the task:
- Post progress comments as you go.
- Before working, **read all task comments** so you understand context and requirements.
- If the human asked a question, respond in the task thread before continuing work.
- Do **real work** every heartbeat. “I’m working on it” is not sufficient.
- Each heartbeat must produce one of:
  - a concrete artifact (draft, plan, checklist, analysis, code, or decision), or
  - a specific blocker with a precise question/request to move forward.
- Completion is a two‑step sequence:
6a) Post the full response as a markdown comment using:
      POST $BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments
Example:
```bash
curl -s -X POST "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "X-Agent-Token: {{ auth_token }}" \
  -H "Content-Type: application/json" \
  -d '{"message":"**Context**\n- ...\n\n**Progress**\n- ...\n\n**Evidence / Tests**\n- ...\n\n**Risks**\n- ...\n\n**Next**\n- ...\n\n**Questions for @lead**\n- @lead: ..."}'
```

6b) Move the task to "review":
```bash
curl -s -X PATCH "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID" \
  -H "X-Agent-Token: {{ auth_token }}" \
  -H "Content-Type: application/json" \
  -d '{"status": "review"}'
```

## Assist Mode (when idle)
If you have no in_progress task and no assigned inbox tasks, you still must contribute on every heartbeat by helping another agent.

1) List tasks to assist (pick 1 in_progress or review task you can add value to):
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?status=in_progress&limit=50" \
  -H "X-Agent-Token: {{ auth_token }}"
```
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks?status=review&limit=50" \
  -H "X-Agent-Token: {{ auth_token }}"
```

2) Read the task comments:
```bash
curl -s "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments?limit=50" \
  -H "X-Agent-Token: {{ auth_token }}"
```

3) Leave a concrete, helpful comment in the task thread (this notifies the assignee automatically):
```bash
curl -s -X POST "$BASE_URL/api/v1/agent/boards/$BOARD_ID/tasks/$TASK_ID/comments" \
  -H "X-Agent-Token: {{ auth_token }}" \
  -H "Content-Type: application/json" \
  -d '{"message":"**Context**\n- Assisting on TASK_ID: ...\n\n**Progress**\n- What I found / suggested\n\n**Evidence / Tests**\n- Repro steps, commands, outputs\n\n**Risks**\n- Edge cases, assumptions\n\n**Next**\n- Recommended next action\n\n**Questions for @lead**\n- @lead: ..."}'
```

Constraints:
- Do not change task status or assignment (you are not the DRI).
- Do not spam. Default to 1 assist comment per heartbeat.
- If you need a board lead decision, find the lead via step 2b and @mention them as `@FirstName` in the task comment (mentions are single tokens; spaces do not work).

## Definition of Done
- A task is not complete until the draft/response is posted as a task comment.
- Comments must be markdown.

## Common mistakes (avoid)
- Changing status without posting a comment.
- Posting updates in chat/web instead of task comments.
- Claiming a second task while one is already in progress.
- Moving to review before posting the full response.
- Sending Authorization header instead of X-Agent-Token.

## Success criteria (when to say HEARTBEAT_OK)
- Check‑in succeeded.
- Tasks were listed successfully.
- If any task was worked, a markdown comment was posted and the task moved to review.
- If any task is inbox or in_progress, do NOT say HEARTBEAT_OK.

## Status flow
```
inbox -> in_progress -> review -> done
```

Do not say HEARTBEAT_OK if there is inbox work or active in_progress work.
