# Idea Coach

A personal, local tool that does only idea work. It turns problems into candidate ideas (Explore),
stress-tests the one you pick (Stress Test), and ends with one small real-world test you can run within a week.

**Project docs update themselves.** `CHANGELOG.md` (history) and `ROADMAP.md` (phases, live status,
guardrails, proposed improvements) are kept current by the app; see "Automatic documentation" below.
Read both before changing anything.

This build covers Phases 1–3 of the revised spec. Phase 4 (experiment log) and Phase 5 (memory) wait
until the prototype passes the baseline comparison. Their database tables already exist.

## Setup (once)

Requires Python 3.10 or later.

```bash
cd idea_coach
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
```

Put your keys in `.env`:

- `ANTHROPIC_API_KEY` from https://platform.claude.com (separate API billing)
- `TAVILY_API_KEY` from https://app.tavily.com (1,000 free searches a month)

Optional but recommended: `git init` and commit. `.env` and `data/` are excluded.

## Run with Docker (recommended)

Needs Docker Desktop (or Docker Engine with Compose). In the `idea_coach` folder:

1. Copy `.env.example` to `.env` and add both keys (one time).
2. Launch:

```bash
docker compose up --build -d
```

Open http://localhost:8501. The app is bound to this computer only.

| Task | Command |
| --- | --- |
| Stop | `docker compose down` |
| View logs | `docker compose logs -f` |
| After changing code or prompts | `docker compose up --build -d` |
| Run the tests | `docker compose run --rm idea-coach pytest` |
| Run the gate check | `docker compose run --rm idea-coach python eval_gate.py` |

Your database (`data/`) and `constraints.md` live in this folder on your computer, so they survive
rebuilds. The container restarts on its own after a reboot until you run `docker compose down`.

## Run without Docker

```bash
streamlit run app.py
```

The database lives in `data/idea_coach.db` and is copied to `data/backups/` every time the app starts
(the newest 10 copies are kept).

## Pages

| Page | What it does |
| --- | --- |
| Explore | Chat about a problem. Up to three different approaches per turn; **Keep** saves one as an idea. |
| Ideas | Status and stage per idea, **Stress test this**, the result, the claim ledger with every status change, and the baseline scoring tab. |
| Baseline | Pass/fail tracker and the instructions to paste into a Claude Project. |
| Runs & costs | Every run and model call with tokens, cost, and latency; verdict distribution. |
| Constraints | Edit `constraints.md`, which the Explorer, Evaluator, and Coach read. |

## How the rules are enforced

| Rule | Where |
| --- | --- |
| Credentials and network identifiers never leave your computer | `gates.py` runs before any API call and blocks the whole message |
| Idea work only, no override | Haiku scope gate on every message; Stress Test needs a saved idea; the Researcher only searches for ledger claims; no agent has code execution |
| Out-of-scope messages are not saved | `pipeline.handle_explore_message` saves messages only after the gate passes; gate inputs are logged as `[not stored]` |
| No `FACT` without a verified source | `ledger.py` downgrades unsupported labels and logs the attempt |
| Every source is checked against its claim | Haiku Source Verifier runs on each evidence record; records citing sources that were not retrieved are dropped |
| The Coach cannot soften blockers | Blockers are copied from the Evaluator by code, not written by the Coach |
| Required output | Pydantic schemas plus a final field check; one repair attempt, then the run fails |
| Run limits | 2 challenge cycles, 5 searches, Opus only when a verdict flips or a critical claim stays decisive and unresolved |
| Cost checkpoint (~$1 or 3 min) | Between cycles, Haiku decides whether another cycle could change the conclusion; if it continues, the run drops to one claim and one search |
| Runaway pause ($5) | The run stops and the Ideas page offers **Continue anyway** |
| Single call timeout (60 s) | One retry with less context; SDK retries are off |

All thresholds, models, effort levels, and prices are in `settings.py`.

## Tests

```bash
pytest                 # offline; uses a fake model and fake search
python eval_gate.py    # live check of the scope gate on 40 labeled messages (a few cents)
```

Watch the "vague seeds wrongly rejected" count in `eval_gate.py`; it should be zero.

## Baseline comparison (Phase 3)

1. On the Baseline page, download the Claude Project instructions and paste them into a new Claude Project.
2. For each of your next 10 real ideas, stress-test it here and give the same idea to the Project.
3. Paste the Project's answer on the idea's Baseline tab and score A vs. B blind.

It passes if the prototype wins at least 6 of 10 and changes a decision or catches a real flaw at least
3 times. If it fails, keep the Claude Project and build only the claim ledger and experiment log.

## Automatic documentation

`devlog.py` updates `CHANGELOG.md` and `ROADMAP.md` with no manual steps.

| Trigger | What gets recorded |
| --- | --- |
| App start (including after `docker compose up --build`) | Any changed file, setting, or prompt since the last start, as a new versioned entry with a Haiku summary |
| Stress Test, baseline score, `eval_gate.py` | Milestones and the roadmap's live status, checks, usage, and suggestions |
| `python update_docs.py` | Everything above, on demand |

The app keeps its comparison snapshot in `data/doc_state/`. `constraints.md` changes are logged as
"changed" but their content is never sent to a model. A diff that trips the security filter is not
sent either; that entry lists files and settings only. Turn off the Haiku summaries with
`AUTO_DOC_AI_SUMMARY = False` in `settings.py`.

## Notes

- Your ideas are sent to Anthropic and Tavily. Only storage is local.
- Explore does not run web searches in this build; facts are checked in Stress Test.
- Prices were checked on November 9, 2026. Update `settings.PRICES` if they change.
