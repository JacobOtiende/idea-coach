# Working on Idea Coach

Before changing anything, read `ROADMAP.md` (phases, guardrails, proposals, decision log) and the most
recent entries in `CHANGELOG.md`.

## Rules

- Keep the Guardrails in `ROADMAP.md`. If a change would break one, stop and ask the user.
- Do not edit inside `<!-- AUTO:... -->` blocks or the entries the app generates. The app records file,
  setting, and prompt changes itself when it next starts.
- After a change, record the **why**, which the app cannot see:
  - Add a row to the Decision log in `ROADMAP.md` for any decision that changes scope, behavior, or a
    guardrail.
  - Update the affected phase section (Built, Expected scope, Done when) and the Proposed improvements
    table.
  - When you complete or add a phase, also add its checks to `devlog.status_block`.
- Run `pytest` before finishing, then `python update_docs.py` so the docs reflect the change.
