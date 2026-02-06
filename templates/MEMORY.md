# MEMORY.md - Long-Term Memory

This is curated knowledge. Update it during consolidation, not constantly during sessions.

Use this for durable facts, decisions, constraints, and recurring patterns. Use `SELF.md` for
evolving identity and preferences.

## SELF (fallback if SELF.md is absent)

If there is no separate `SELF.md` in this workspace, keep evolving identity/preferences here.
Update during consolidation, not constantly.

- Preferences / working style:
- What I learned about the human:
- What changed recently:

{% if board_id is defined %}
## Board Context (read-only unless board goal changes)

- Board: {{ board_name }}
- Board type: {{ board_type }}
- Objective: {{ board_objective }}
- Success metrics: {{ board_success_metrics }}
- Target date: {{ board_target_date }}
{% endif %}

## Constraints / Assumptions

- [Add constraints that affect decisions and task execution]

## Decisions (with rationale)

- [Decision] - [Why]

## Known Risks / Open Questions

- [Risk or question] - [Mitigation or next step]

## Useful References

- [Commands, paths, URLs (without secrets)]

---

Last consolidated: [YYYY-MM-DD]
