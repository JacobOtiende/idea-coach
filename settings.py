"""Central settings: models, prices, limits, paths. Edit values here, not in code."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR = BASE_DIR / "data"
DB_PATH = Path(os.getenv("IDEA_COACH_DB", DATA_DIR / "idea_coach.db"))
BACKUP_DIR = DATA_DIR / "backups"
BACKUPS_TO_KEEP = 10
PROMPT_DIR = BASE_DIR / "prompts"
CONSTRAINTS_PATH = BASE_DIR / "constraints.md"

# Project docs, kept up to date automatically by devlog.py.
CHANGELOG_PATH = Path(os.getenv("IDEA_COACH_CHANGELOG", BASE_DIR / "CHANGELOG.md"))
ROADMAP_PATH = Path(os.getenv("IDEA_COACH_ROADMAP", BASE_DIR / "ROADMAP.md"))
DOC_STATE_DIR = Path(os.getenv("IDEA_COACH_DOC_STATE", DATA_DIR / "doc_state"))
# Describe detected code changes in plain words with Haiku (a fraction of a cent each).
AUTO_DOC_AI_SUMMARY = True

# Major prompt version. Runs also record a fingerprint of the prompt text, so any
# prompt edit is tracked automatically without changing this number.
PROMPT_VERSION = "1.0"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# --- Models -----------------------------------------------------------------
MODELS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

# USD per million tokens. Checked 2026-11-09 against
# https://platform.claude.com/docs/en/about-claude/pricing
PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write": 0.125, "cache_read": 0.01},
    # Haiku 5.5 prompts over 100K tokens use higher prices.
    "claude-haiku-5-5-long": {"input": 0.50, "output": 2.50, "cache_write": 0.625, "cache_read": 0.05},
    "claude-sonnet-5-5": {"input": 2.00, "output": 10.00, "cache_write": 2.50, "cache_read": 0.10},
    "claude-opus-5-5": {"input": 4.00, "output": 20.00, "cache_write": 5.00, "cache_read": 0.20},
}
HAIKU_LONG_PROMPT_TOKENS = 100_000

# Tavily basic search: 1 credit, 1,000 free credits a month, then $0.008 a credit.
SEARCH_COST_USD = 0.0  # set to 0.008 once past the free tier

# agent name -> (model tier, effort). The baseline comparison moves agents up or down.
AGENT_MODELS = {
    "scope_gate": ("haiku", "low"),
    "claim_extractor": ("haiku", "medium"),
    "source_verifier": ("haiku", "medium"),
    "reconsider": ("haiku", "low"),
    "explorer": ("sonnet", "medium"),
    "researcher_plan": ("sonnet", "low"),
    "researcher": ("sonnet", "medium"),
    "challenger": ("sonnet", "medium"),
    "counter_challenger": ("sonnet", "medium"),
    "evaluator": ("sonnet", "high"),
    "coach": ("sonnet", "medium"),
    "doc_summarizer": ("haiku", "low"),
    "doc_reader": ("haiku", "medium"),
}

# max_tokens covers thinking plus the reply. Tier default, used when an agent has no entry below.
MAX_TOKENS = {"haiku": 4000, "sonnet": 16000, "opus": 16000}

# Default output cap per agent: the low value every call starts from. When a reply is cut off
# at this cap, that one call is retried once at RETRY_MAX_TOKENS, and the next call starts low again.
# Thinking tokens count against the cap too.
AGENT_MAX_TOKENS = {
    "scope_gate": 300,
    "reconsider": 400,
    "doc_summarizer": 800,
    "researcher_plan": 1000,
    "source_verifier": 1000,
    "claim_extractor": 2500,
    "counter_challenger": 3000,
    "researcher": 3000,
    "explorer": 3500,
    "coach": 6000,
    "challenger": 4000,
    "evaluator": 8000,
    "doc_reader": 2500,
}

# Ceiling for the single retry of a call that was cut off at its default cap. Used only then.
RETRY_MAX_TOKENS = {"haiku": 8000, "sonnet": 16000, "opus": 16000}

# --- Run limits ---------------------------------------------------------------
MAX_CHALLENGE_CYCLES = 2
MAX_SEARCHES_PER_RUN = 5
MAX_CRITICAL_CLAIMS_RESEARCHED = 3
MAX_EVIDENCE_PER_CLAIM = 3

# Step limit: model calls per Stress Test run. Counted in RunContext; checked before optional
# work only. Source verification and the final Evaluator and Coach passes are never skipped.
MAX_STEPS = 30
STEPS_PER_RESEARCH = 2 + MAX_CRITICAL_CLAIMS_RESEARCHED * MAX_EVIDENCE_PER_CLAIM  # plan, researcher, verifiers
STEPS_PER_CYCLE = STEPS_PER_RESEARCH + 3  # plus challenger, counter-challenger, evaluator
FINAL_STEPS_RESERVE = 4  # coach, Opus re-evaluation, and up to two repairs

# --- Cost and latency controls (starting estimates; tune from the Runs page) ---
RECONSIDER_COST_USD = 1.00
RECONSIDER_SECONDS = 180
CALL_TIMEOUT_SECONDS = 60
RUNAWAY_PAUSE_USD = 5.00

# Explore history sent to the model (messages).
EXPLORE_HISTORY_MESSAGES = 6

# Uploaded documents in Explore.
DOC_MAX_BYTES = 5_000_000
DOC_MAX_CHARS = 60_000  # longer text is cut here, and the user is told
DOC_SCOPE_EXCERPT_CHARS = 3_000  # the scope gate sees only this much before the document is read in full
