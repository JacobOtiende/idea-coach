# Changelog

The development history of Idea Coach, newest first. Read this file and `ROADMAP.md` before any change.

## How this file is maintained

You never need to edit this file. The app updates it on its own (`devlog.py`):

- **Code, prompt, and setting changes.** Each time the app starts, it compares every project file and
  setting with the last recorded state. Any difference becomes a new versioned entry: a plain-language
  summary written by Haiku, the files that changed, every setting's old and new value, and the new
  prompt version. Without an API key, the entry lists files and settings only.
- **Milestones from real use.** The first live Stress Test, each scope gate check, phase status changes,
  and the baseline result are added as dated entries.
- **When it runs.** At app start, after each Stress Test, after baseline scoring, after
  `python eval_gate.py`, and on demand with `python update_docs.py`.

Version numbers increase automatically. Entries are inserted below the marker line. Your own notes
anywhere else in this file are kept.

<!-- AUTO-ENTRIES: new entries are inserted below this line -->

## 0.3.6 · 2026-11-09 22:03 · Recorded automatically

### Added
- Calls whose reply stopped at max_tokens are logged with status "truncated" instead of "ok", so truncated replies are visible on the Runs page.
- A test suite covers the truncation retry: a cut-off reply is retried once at the higher ceiling, the next call starts from the default cap again, and a complete reply is not retried.

### Changed
- Agent calls now start with lower output caps, and a reply cut off at max_tokens is retried once at a higher ceiling (RETRY_MAX_TOKENS) before being returned; the scope gate default drops to 300 and doc_reader drops to 2500, so these agents may hit the retry more often.

### Files
- Changed: `llm.py`
- Changed: `settings.py`
- Changed: `tests/test_limits.py`

### Settings
- `AGENT_MAX_TOKENS`: `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_reader": 6000, "doc_sum...` → `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_reader": 2500, "doc_sum...`
- `RETRY_MAX_TOKENS`: (none) → `{"haiku": 8000, "opus": 16000, "sonnet": 16000}`

## 0.3.5 · 2026-11-09 21:51 · Recorded automatically

### Fixed
- The scope gate agent now has a 1000-token output limit instead of 300, so its responses are no longer cut off; a logged call had used 427 output tokens.
- The doc reader agent now has a 6000-token output limit instead of 2500, so briefs for long documents are no longer truncated mid-JSON.

### Files
- Changed: `settings.py`

### Settings
- `AGENT_MAX_TOKENS`: `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_reader": 2500, "doc_sum...` → `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_reader": 6000, "doc_sum...`

## 0.3.4 · 2026-11-09 21:32 · Recorded automatically

### Changed
- Project files changed; see the file list below.

### Files
- Added: `tests/test_documents.py`

## 0.3.3 · 2026-11-09 21:32 · Recorded automatically

### Added
- Explore can now read an uploaded .txt, .md, or .pdf file (up to 5 MB) and generate ideas from a brief of its contents, with an optional focus note.
- A new doc_reader agent writes a structured brief (summary, key points, problems, ideas mentioned, open questions) that later Explore turns in the same session can draw on.
- Documents are checked by the security filter in full and by the scope gate on their first 3,000 characters; out-of-scope documents are rejected before the full text is sent to the model.
- Documents longer than 60,000 characters are cut off, and the user is told only the first part was read.

### Changed
- The Explore message handler now accepts the current document brief and name, and the explorer prompt includes the brief as separate material when one exists.

### Files
- Added: `documents.py`
- Added: `prompts/doc_reader.txt`
- Changed: `agents.py`
- Changed: `app.py`
- Changed: `pipeline.py`
- Changed: `requirements.txt`
- Changed: `settings.py`

### Settings
- `AGENT_MAX_TOKENS`: `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_summarizer": 800, "eval...` → `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_reader": 2500, "doc_sum...`
- `AGENT_MODELS`: `{"challenger": ["sonnet", "medium"], "claim_extractor": ["haiku", "medium"], "coach": ["sonnet", "medium"], "counter_...` → `{"challenger": ["sonnet", "medium"], "claim_extractor": ["haiku", "medium"], "coach": ["sonnet", "medium"], "counter_...`
- `DOC_MAX_BYTES`: (none) → `5000000`
- `DOC_MAX_CHARS`: (none) → `60000`
- `DOC_SCOPE_EXCERPT_CHARS`: (none) → `3000`

### Prompts
- Prompt version `1.0+ae6dc3` → `1.0+df110f`. Runs on each version are listed separately on the Runs & costs page.

## 0.3.2 · 2026-11-09 21:11 · Recorded automatically

### Added
- Stress Test now caps output length per agent (for example, the scope gate and reconsideration checks get small limits, while the evaluator and coach get larger ones), which lowers worst-case output cost without changing normal replies.
- Stress Test now enforces a per-run limit of 30 model calls, skipping optional research or an extra challenge cycle when too few calls remain for the final evaluator, coach, and repair passes.
- Tests cover per-agent output caps, the tier fallback for agents without a cap, step counting, and skipping research when the step limit would leave no room for final passes.

### Changed
- Documentation sync tests and file reads/writes now explicitly use UTF-8 encoding, which does not change app behavior.

### Files
- Added: `tests/test_limits.py`
- Changed: `llm.py`
- Changed: `pipeline.py`
- Changed: `settings.py`
- Changed: `tests/test_devlog.py`

### Settings
- `AGENT_MAX_TOKENS`: (none) → `{"challenger": 4000, "claim_extractor": 2500, "coach": 6000, "counter_challenger": 3000, "doc_summarizer": 800, "eval...`
- `FINAL_STEPS_RESERVE`: (none) → `4`
- `MAX_STEPS`: (none) → `30`
- `STEPS_PER_CYCLE`: (none) → `14`
- `STEPS_PER_RESEARCH`: (none) → `11`

## 0.3.1 · 2026-11-10 02:27 · Recorded automatically

### Changed
- The devlog test suite no longer passes an explicit UTF-8 encoding when reading and writing the CHANGELOG and ROADMAP files; behavior is unchanged.

### Files
- Changed: `tests/test_devlog.py`

## 2026-11-09 20:21 · Milestone: automatic documentation started

- Tracking 42 project files and 18 settings.
- Prompt version `1.0+ae6dc3`.

## 0.3.0 · 2026-11-09 · Automatic documentation

### Added
- `devlog.py` keeps `CHANGELOG.md` and `ROADMAP.md` current with no manual steps: change detection
  for files, settings, and prompts; Haiku summaries of each change; milestones from real use; live
  phase status, usage numbers, and data-driven improvement suggestions in the roadmap.
- `update_docs.py` to run the update on demand.
- `gate_evals` table; `eval_gate.py` now saves each result and updates the docs.
- `CLAUDE.md`, so AI-assisted changes read both docs first and record decisions.
- Docker mounts for both docs, so updates made inside the container appear in your folder.

### Changed
- Runs record the prompt version as the major version plus a fingerprint of the prompt text (for
  example `1.0+3fa2c1`), so prompt edits are tracked without a manual version bump.

## 0.2.0 · 2026-11-09 · Docker

### Added
- `Dockerfile` (Python 3.12 slim, Streamlit health check).
- `docker-compose.yml`: one-command launch with `docker compose up --build -d`, bound to
  127.0.0.1:8501, keys from `.env`, `data/` and `constraints.md` mounted from the host, restarts
  automatically.
- `.dockerignore` so `.env` and `data/` never enter the image.
- README section with Docker commands for stop, logs, rebuild, tests, and the gate check.

### Notes
- `docker compose config` passed. A full image build was not tested in the build environment because
  it could not pull the base image from Docker Hub.

## 0.1.0 · 2026-11-09 · Phases 1–3

### Added
- **Phase 1:** constraints file, local security filter (Gate 1), Haiku scope gate (Gate 2), Explore
  mode, idea pipeline with statuses, run and call logging with cost, SQLite with backup on start.
- **Phase 2:** Stress Test with claim extraction, research via Tavily, source verification, claim
  ledger enforced in code, Challenger, Counter-Challenger, Evaluator with stage-specific bars, Coach
  result with required fields.
- **Phase 3:** blind A/B baseline scoring, pass/fail tracker, downloadable Claude Project instructions.
- Cost and latency controls: checkpoint at about $1 or 3 minutes between cycles, runaway pause at $5,
  60-second call timeout with one smaller retry, Opus escalation on verdict flip or decisive unresolved
  claim.
- Tables for Phases 4 and 5 (`experiments`, `concepts`, `lessons`, `relationships`, `memory_fts`),
  unused so far.
- Tests: offline tests with a fake model and fake search; `eval_gate.py` with 40 labeled gate cases
  for a live check.

### Decisions
- Built only Phases 1–3. Phases 4 and 5 wait for the baseline comparison.
- Explore does not search the web in this build; facts are checked in Stress Test.
- Structured output uses JSON in text, validated by Pydantic with one repair attempt, because
  Sonnet 5.5 restricts forced tool use.
- Checkpoints are taken between cycles, so the first research-and-challenge cycle always completes.
- A vague seed that is still unclear after one clarifying question is treated as in scope, because
  wrongly rejecting seeds is the worse error.
- Gate inputs are logged as `[not stored]` until a message passes the scope gate.

## 0.0.1 · 2026-11-09 · Revised spec

### Decisions
- Reviewed the original architecture and agent prompt specification and revised it into the
  "Idea Coach Revised Spec" doc.
- Personal tool only, idea work only, enforced in code with no override.
- Two modes: Explore (default) and Stress Test (on a button).
- Claim ledger enforces fact labels in code; Evaluator uses separate bars for early and later ideas;
  convergence guard on narrowed ideas.
- No fixed price limit. Use the cheapest model that holds quality; reconsider calls when runs get slow
  or expensive; pause at $5 a run as a guard against bugs.
- Off-limits: all data considered sensitive to cyber attack.
- Original spec's Idea Developer folded into the Coach result; Knowledge Curator becomes a Memory
  Tagger plus user approval in Phase 5.
