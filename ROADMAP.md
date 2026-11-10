# Roadmap and build notes

What is built, what each phase must deliver, and what may come next. Read this file with
`CHANGELOG.md` before any change.

## How this file is maintained

You never need to edit this file. The **Live status** block below is rewritten by the app
(`devlog.py`) at start, after each Stress Test, after baseline scoring, and after the gate check. It
ticks each phase's checks from real data, shows usage numbers, and adds **Suggested by usage data**
items when the numbers point to an improvement (for example, one verdict dominating, costs above the
checkpoint, or the scope gate missing cases). Phase status changes are also logged in `CHANGELOG.md`.

The sections outside the Live status block describe intent and are updated when the plan changes. When
Claude makes changes to this project, `CLAUDE.md` tells it to update them and the decision log.

## Live status

<!-- AUTO:status:start -->
_Generated 2026-11-09 22:03 from the app's data. Edits inside this block are overwritten._

| Phase | Name | Status |
| --- | --- | --- |
| 1 | Gates, Explore, idea pipeline | Built; checks pending |
| 2 | Stress Test and claim ledger | Built; first live run pending |
| 3 | Baseline comparison | In progress (0 of 10 ideas) |
| 4 | Experiment log | Blocked on Phase 3 |
| 5 | Memory | Blocked on Phase 4 |

**Phase 1 checks**
- [ ] Explore session saved an idea
- [ ] Live gate check passed (`python eval_gate.py`)

**Phase 2 checks**
- [x] No `FACT` without verified evidence (unit tests)
- [x] A run ends with one small test (unit tests)
- [ ] First live Stress Test completed

**Phase 3 checks**
- [ ] 10 real ideas scored (0 so far)
- [ ] At least 6 prototype wins (0 so far)
- [ ] At least 3 changed decisions or caught flaws (0 so far)

**Usage**

- Ideas: none yet
- Stress Tests: 0 completed, 0 paused, 0 failed
- API spend to date: $0.13

**Suggested by usage data**

- Nothing yet. Suggestions appear as real runs accumulate.
<!-- AUTO:status:end -->

## Guardrails

These hold for every phase.

- Idea work only, enforced in code. No override switch.
- Nothing matching the security filter reaches an API or the database.
- No claim becomes `FACT` without a source that verification confirmed.
- The Coach cannot drop or soften the Evaluator's blockers.
- Memory never builds a profile of the user, and nothing is saved to memory without approval.
- The never-cut steps stay: security filter, scope gate, source verification, final Evaluator pass,
  statements of uncertainty.
- The tool is judged by whether it changes decisions, not by how thorough it sounds.

## Phase 1 · Gates, Explore, idea pipeline (built)

**Goal:** a safe, focused place to turn problems into ideas.

**Built**
- `constraints.md`, editable on the Constraints page.
- Gate 1 (`gates.py`): blocks credentials, keys, tokens, IP and hardware addresses, internal hostnames.
- Gate 2: Haiku scope gate on every message, one clarifying question for unclear messages, fixed
  rejection line.
- Explore: up to three structurally different approaches; **Keep** saves an idea as `captured`.
- Idea statuses `captured`, `exploring`, `testing`, `killed` (reason required), `shipped`.
- Logging of every run and model call with tokens, cost, and latency.

**Done when:** an Explore session saves an idea, and `python eval_gate.py` gets at least 90% of the 40
labeled cases right with zero vague seeds wrongly rejected.

## Phase 2 · Stress Test and claim ledger (built)

**Goal:** an honest critique of one idea that ends in one small real-world test.

**Built**
- Claim extraction, research planning (5 searches max), Tavily search, evidence records tied to
  retrieved sources only, Haiku source verification.
- Claim ledger rules in `ledger.py`, with every change and refused label logged.
- Challenger (top 3 objections), Counter-Challenger, Evaluator with early and later bars,
  convergence guard, 2 cycles max.
- Coach result with required fields; blockers copied by code.
- Checkpoint, runaway pause, timeout retry, Opus escalation.

**Done when:** the ledger rules pass their unit tests and the first live Stress Test completes.

## Phase 3 · Baseline comparison (tool built)

**Goal:** prove the pipeline beats one well-prompted Claude before building more.

**Built**
- Claude Project instructions export on the Baseline page.
- Blind A/B scoring per idea, labels revealed after scoring.
- Pass tracker: 10 ideas, at least 6 prototype wins, at least 3 changed decisions or caught flaws.

**Done when:** 10 real ideas are scored. The result is logged automatically.

**If it passes:** start Phase 4.
**If it fails:** keep using the Claude Project for critique and build only the claim ledger and
experiment log around it. Rewrite Phases 4 and 5 here before building.

**Also use the comparison to tune models.** For each agent, check whether a cheaper model holds
quality on its cases and update `AGENT_MODELS` in `settings.py`. The change is logged automatically.

## Phase 4 · Experiment log (expected)

**Goal:** record what happened when you ran the smallest test, so claims and lessons rest on real
results instead of model output.

**Expected scope**
- "Start this test" on a Stress Test result creates an `experiments` row with hypothesis, success
  criteria, and failure criteria copied from the result; idea moves to `testing`.
- Log a result: outcome text, date, and whether it met success or failure criteria.
- A logged result adds evidence of type `user_experiment` to the linked claims and re-applies the
  ledger rules.
- Draft a Lesson from the result and from any kill reason; saved only after approval.
- Experiments view on the Ideas page, with overdue tests highlighted.
- Re-running Stress Test after a result uses the updated ledger.
- Add Phase 4 checks to `devlog.status_block`.

**Done when:** a logged result changes the status of its linked claims, with the event in the ledger
history, and a killed idea's reason can become an approved Lesson.

## Phase 5 · Memory (expected)

**Goal:** reuse past concepts and lessons across ideas without treating them as truth.

**Expected scope**
- Memory Tagger (Haiku) proposes abstract pattern tags, such as "triage under uncertainty", for
  concepts and lessons; nothing is saved until approved.
- `memory_fts` search over content and tags, then a model reranks matches.
- Retrieved items enter Explore and Stress Test as suggestions, labeled as recalled and re-entering
  the ledger as `HYPOTHESIS` unless revalidated.
- Superseded items are marked and linked, never overwritten.
- Memory library page to review, approve, edit, and supersede items.
- Add Phase 5 checks to `devlog.status_block`.

**Done when:** an approved concept is retrieved for an idea in a different domain and goes back through
validation, and a test proves nothing reaches memory without approval.

## Proposed improvements

Candidates only. Each needs a decision before it becomes a phase. Data-driven suggestions appear in the
Live status block above.

| Proposal | Why | Depends on |
| --- | --- | --- |
| Web search in Explore (max 2 searches, off by default) | Catch a fact that would change direction early | Phase 3 cost data |
| Resume a paused run instead of restarting it | **Continue anyway** currently reruns from the start | None |
| Prompt evaluation set | Fixed ideas with known flaws, rerun after each prompt change to catch regressions | Phase 3 cases |
| Evaluator calibration | Retune bars if one verdict dominates | 10+ real runs |
| Effort tuning per agent | Lower effort where quality holds to cut cost and time | Phase 3 cases |
| Export a result as Markdown | Share or archive a Stress Test outside the app | None |
| Idea comparison view | Rank several ideas on the same criteria before choosing one to test | Phase 4 |
| Weekly review | List ideas stuck in `exploring` or tests past their date | Phase 4 |
| Local model for Gate 2 | Keep scope checks fully offline | Gate check results |

## Known limitations

- Not yet run against the live Anthropic or Tavily APIs.
- Docker image build not tested end to end in the build environment.
- Structured output relies on JSON in text with one repair; revisit if a native structured-output
  method becomes available for Sonnet 5.5.
- The security filter only recognizes patterns. Descriptions of real systems remain your responsibility.
- Prices in `settings.py` were checked on 2026-11-09 and need manual updates.
- Automatic change entries describe what changed, not why. The reason is recorded only when the change
  is made through Claude (see `CLAUDE.md`).

## Decision log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-11-09 | Build Phases 1–3 only | Prove the pipeline beats a baseline before adding scope |
| 2026-11-09 | Checkpoints between cycles, not mid-cycle | The first cycle is the minimum useful result |
| 2026-11-09 | No fixed price limit; pause at $5 a run | User preference; the pause guards against bugs |
| 2026-11-09 | Docker Compose as the main way to run | User request for a one-command launch |
| 2026-11-09 | Docs maintained automatically by the app | User request: no manual updates |
| 2026-11-09 | Explore accepts an uploaded .txt, .md, or .pdf. It is checked by Gate 1 in full and by the scope gate on its first 3,000 characters, then read by a Haiku `doc_reader` into a brief that the Explorer uses | Lets Explore start from real material. The full text is sent only after both gates pass; the brief lasts for the session |
| 2026-11-09 | Output caps start low per agent. A reply cut off at its cap is retried once at `RETRY_MAX_TOKENS`; the next call starts low again | Keeps normal calls cheap. Raising the default for everyone would raise cost on every call, not only the rare long ones |
| 2026-11-09 | Per-agent `max_tokens` caps and a 30-call step limit per Stress Test | Cut worst-case output cost. Step limit only skips optional work (cycles 2+ and research); source verification, the final Evaluator and Coach always run |
