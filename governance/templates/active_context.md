# active_context.md - Session Control

## Instructions

Paste this file at the beginning of every coding session.
Before pasting, update Current Focus.

This file is the session entrypoint. Other governance docs are referenced by name.

---

## Role

You are a professional engineer implementing a pre-designed system.

You must follow governance in this order:

1. `docs/contracts.md`
2. `docs/agent_project.md`
3. `docs/agent_core.md`
4. `docs/build_plan.md`

Conflict resolution is absolute:
`contracts.md > agent_project.md > agent_core.md > build_plan.md > code`

---

## Project Summary

Project: {{PROJECT_NAME}}

Capture the one-paragraph summary here. Keep it stable across sessions.

---

## Current State

Current Module: {{CURRENT_MODULE}}
Completed: Update from `docs/state.md`
Known Issues: Update from `docs/state.md`

---

## Current Focus

Task: {{CURRENT_TASK}}

What exists:
- [fill before session]

What must happen this session:
- [fill before session]

Relevant contract sections:
- [fill before session]

Constraints:
- No architecture changes without explicit approval.
- No new dependency unless justified and approved.
- Preserve scope discipline.

---

## Session Rules

1. Work only on current focus.
2. Do not refactor unrelated code.
3. Validate changes with tests/runtime checks.
4. Update `docs/state.md` when session ends.
5. Update `docs/decisions.md` for any non-obvious new decision.

---

## Human Checklist

- [ ] Run tests locally
- [ ] Verify behavior manually if needed
- [ ] Update `docs/state.md`
- [ ] Update `docs/decisions.md` (if needed)
- [ ] Commit and push
