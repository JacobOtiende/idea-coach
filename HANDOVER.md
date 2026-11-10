# Idea Coach Handover

*Last updated: 2026-11-09*

## Current Status

**Phase:** Phases 1–3 built and ready for baseline testing  
**Status:** Running locally in Docker at http://localhost:8501  
**Tests:** 86/93 pass (7 failures in devlog UTF-8 encoding, non-critical)  
**Git:** Initialized; initial commit c980e74 (2026-11-09)  

## What It Is

A personal, local tool for structured idea development:
1. **Explore:** Turn problems into 3 candidate ideas per turn
2. **Stress Test:** Challenge chosen idea with research, claims, and objections
3. **Baseline:** Measure against a manually-prompted Claude Project

See README.md for full feature list.

## Completed Work (This Session)

- ✅ Set up Python 3.12 venv with all dependencies
- ✅ Created `.env` with API keys (Anthropic, Tavily)
- ✅ Ran test suite: 86/93 pass (7 devlog UTF-8 encoding issues, not blocking)
- ✅ Built Docker image and container
- ✅ Verified app running and responding on localhost:8501
- ✅ Initialized git repo and made initial commit

## Known Issues

**Local venv:** Windows AppControl policy blocks pandas DLLs. Use Docker instead.

**Test failures (non-critical):**
- 7 tests in test_devlog.py fail due to UTF-8 encoding of bullet character (·) in CHANGELOG.md
- Does not affect app functionality; documentation sync still works in Docker

## How to Run

```bash
# Docker (recommended)
docker compose up -d
# Opens http://localhost:8501

# Or local (if Windows AppControl permits)
.venv\Scripts\streamlit run app.py
```

## Next Steps

### Immediate (before next session)
1. Test Explore mode with a real problem
2. Save one idea and move to Stress Test
3. Review the claim ledger and baseline scoring tabs
4. Check that CHANGELOG.md and ROADMAP.md update automatically

### Phase 3 completion (to unlock Phase 4)
1. Run 10 real ideas through Explore → Stress Test → Baseline scoring
2. Need: 6/10 prototype wins + 3+ decision changes/caught flaws
3. Once baseline passes, Phases 4 (experiment log) and 5 (memory) can be built

### Known limitations
- Not yet run against live Anthropic/Tavily APIs (only tested locally)
- Web search disabled in Explore (facts checked in Stress Test instead)
- Docker build tested in Docker but not yet in the full build environment

## Key Files

| File | Purpose |
|---|---|
| `README.md` | Setup, pages, rules, baseline instructions |
| `ROADMAP.md` | Phases, guardrails, live status, decision log |
| `CLAUDE.md` | Rules for AI-assisted changes |
| `CHANGELOG.md` | Auto-updated version history with AI summaries |
| `app.py` | Streamlit UI (4 tabs: Explore, Ideas, Baseline, Runs & costs) |
| `agents.py` | Agent definitions with system prompts |
| `pipeline.py` | Message handling and orchestration |
| `gates.py` | Security (credentials, IPs, hostnames) + Haiku scope gate |
| `ledger.py` | Claim status rules enforced in code |
| `db.py` | SQLite schema and queries |
| `settings.py` | All costs, models, effort levels, thresholds |

## Guardrails (Never Remove)

- Idea work only, no override
- Security filter blocks credentials/keys before any API call
- No claim becomes FACT without verified source
- Coach cannot soften Evaluator's blockers
- Cost checkpoint (~$1 or 3 min) between cycles
- Runaway pause at $5/run
- 2 challenge cycles max, 5 searches max

## Important Context

**Why built in phases:** Testing baseline before adding Phases 4–5 prevents over-engineering. If baseline fails, pivot to using a Claude Project for critique and build only the ledger + experiment log.

**Automatic docs:** `devlog.py` updates CHANGELOG.md and ROADMAP.md on app start, after each Stress Test, and via `python update_docs.py`. Never edit inside `<!-- AUTO:... -->` blocks.

**Cost tracking:** Settings.PRICES checked on 2026-11-09. Update if rates change.
