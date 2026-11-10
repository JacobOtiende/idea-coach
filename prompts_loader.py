"""Builds system prompts: shared rules (cached) + the agent's role + its output schema."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from pydantic import BaseModel

import settings

# Agents that share a role file.
_ROLE_FILES = {"researcher_plan": "researcher_plan", "researcher": "researcher"}


@lru_cache(maxsize=None)
def read_prompt(name: str) -> str:
    return (settings.PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def read_constraints() -> str:
    try:
        return settings.CONSTRAINTS_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return "(No constraints file found.)"


def prompt_version() -> str:
    """Major version plus a short hash of every prompt file, e.g. '1.0+3fa2c1'."""
    h = hashlib.sha256()
    for path in sorted(settings.PROMPT_DIR.glob("*.txt")):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return f"{settings.PROMPT_VERSION}+{h.hexdigest()[:6]}"


# Internal maintenance agents do not get the idea-work rules.
_NO_SHARED_RULES = {"doc_summarizer"}


def system_blocks(agent: str, schema: type[BaseModel] | None = None) -> list[dict]:
    role = read_prompt(_ROLE_FILES.get(agent, agent))
    if schema is not None:
        role += (
            "\n\nOUTPUT FORMAT\n\nReturn only one JSON object that matches this JSON schema. "
            "No prose outside the JSON.\n\n" + json.dumps(schema.model_json_schema(), indent=1)
        )
    if agent in _NO_SHARED_RULES:
        return [{"type": "text", "text": role, "agent": agent}]
    return [
        {"type": "text", "text": read_prompt("shared_rules"), "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": role, "agent": agent},
    ]


def baseline_project_instructions() -> str:
    """One text block to paste into a Claude Project for the baseline comparison."""
    parts = [read_prompt("shared_rules")]
    for name in ("explorer", "challenger", "counter_challenger", "evaluator", "coach"):
        parts.append(f"--- {name.upper()} ROLE (apply this thinking yourself) ---\n" + read_prompt(name))
    parts.append(
        "--- HOW TO RESPOND IN THIS PROJECT ---\n"
        "When I give you an idea, stress-test it in one reply: list its critical claims and their "
        "epistemic status, research them on the web, raise the top three objections, test those "
        "objections, give a verdict, list unresolved blockers, say what distinctive value narrowing "
        "removed, and end with one small test I could run within a week plus success and failure criteria."
    )
    parts.append("--- MY CONSTRAINTS ---\n" + read_constraints())
    return "\n\n".join(parts)
