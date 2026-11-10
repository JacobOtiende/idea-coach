"""Provider adapter, cost metering, structured output, and run-level controls.

Agents never call the Anthropic SDK directly. They go through RunContext.call(),
which logs every call, adds up cost, enforces the runaway pause, retries a
timed-out call once with less context, and validates JSON output with Pydantic.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

import settings
from prompts_loader import system_blocks

T = TypeVar("T", bound=BaseModel)


# --- errors -----------------------------------------------------------------
class LLMTimeout(Exception):
    """A single model call exceeded the timeout."""


class AgentOutputError(Exception):
    """An agent's output failed validation after one repair attempt."""


class RunawayPause(Exception):
    """The run reached the runaway limit and needs the user's approval to continue."""


class SearchUnavailable(Exception):
    """No search provider is configured."""


# --- provider interface ---------------------------------------------------------
@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class LLMResponse:
    text: str
    usage: Usage
    model: str
    truncated: bool = False  # True when the reply stopped at max_tokens before it finished


class Provider(Protocol):
    def complete(self, *, model: str, system: list[dict], messages: list[dict], max_tokens: int,
                 effort: str, timeout: float) -> LLMResponse: ...


class AnthropicProvider:
    """Claude API through the official SDK. SDK retries are off; RunContext owns retry policy."""

    def __init__(self, api_key: str | None = None):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(
            api_key=api_key or settings.ANTHROPIC_API_KEY,
            timeout=settings.CALL_TIMEOUT_SECONDS,
            max_retries=0,
        )

    def complete(self, *, model, system, messages, max_tokens, effort, timeout) -> LLMResponse:
        # Blocks carry an internal "agent" label; the API accepts only these keys.
        clean_system = [{k: v for k, v in b.items() if k in ("type", "text", "cache_control")} for b in system]
        try:
            resp = self.client.with_options(timeout=timeout).messages.create(
                model=model,
                max_tokens=max_tokens,
                system=clean_system,
                messages=messages,
                output_config={"effort": effort},
            )
        except self._anthropic.APITimeoutError as exc:
            raise LLMTimeout(str(exc)) from exc
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        u = resp.usage
        usage = Usage(
            input_tokens=u.input_tokens or 0,
            output_tokens=u.output_tokens or 0,
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
        )
        truncated = getattr(resp, "stop_reason", "") == "max_tokens"
        return LLMResponse(text=text, usage=usage, model=model, truncated=truncated)


def compute_cost(model: str, usage: Usage) -> float:
    prompt_tokens = usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens
    key = model
    if model == settings.MODELS["haiku"] and prompt_tokens > settings.HAIKU_LONG_PROMPT_TOKENS:
        key = f"{model}-long"
    p = settings.PRICES.get(key)
    if p is None:
        return 0.0
    return (
        usage.input_tokens * p["input"]
        + usage.output_tokens * p["output"]
        + usage.cache_read_tokens * p["cache_read"]
        + usage.cache_write_tokens * p["cache_write"]
    ) / 1_000_000


# --- JSON handling ---------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Pull a JSON object out of model text: a fenced block first, else the outermost braces."""
    for candidate in _FENCE.findall(text):
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


# --- run context ---------------------------------------------------------------
@dataclass
class RunContext:
    db: Any
    provider: Provider
    run_id: int
    searcher: Any = None
    allow_runaway: bool = False
    started: float = field(default_factory=time.monotonic)
    cost: float = 0.0
    searches: int = 0
    steps: int = 0  # model calls made in this run, including retries and repairs
    checkpoint_handled: bool = False
    degraded: bool = False
    store_inputs: bool = True

    # cost and time ------------------------------------------------------------
    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def checkpoint_due(self) -> bool:
        if self.checkpoint_handled:
            return False
        return self.cost >= settings.RECONSIDER_COST_USD or self.elapsed >= settings.RECONSIDER_SECONDS

    def _check_runaway(self) -> None:
        if not self.allow_runaway and self.cost >= settings.RUNAWAY_PAUSE_USD:
            raise RunawayPause(f"Run reached ${self.cost:.2f}, the runaway limit of ${settings.RUNAWAY_PAUSE_USD:.2f}.")

    @property
    def searches_left(self) -> int:
        return max(0, settings.MAX_SEARCHES_PER_RUN - self.searches)

    @property
    def steps_left(self) -> int:
        return max(0, settings.MAX_STEPS - self.steps)

    # search -------------------------------------------------------------------
    def search(self, query: str) -> list[dict]:
        if self.searcher is None:
            raise SearchUnavailable("No search provider configured.")
        if self.searches_left <= 0:
            return []
        self._check_runaway()
        self.searches += 1
        results = self.searcher.search(query)
        self.cost += settings.SEARCH_COST_USD
        self.db.insert("searches", run_id=self.run_id, query=query, result_count=len(results))
        return results

    # model calls ---------------------------------------------------------------
    def _log(self, agent, model, effort, usage: Usage | None, cost, latency, status, input_text, output_text):
        u = usage or Usage()
        self.db.insert(
            "llm_calls", run_id=self.run_id, agent=agent, model=model, effort=effort,
            input_tokens=u.input_tokens, output_tokens=u.output_tokens,
            cache_read_tokens=u.cache_read_tokens, cache_write_tokens=u.cache_write_tokens,
            cost=round(cost, 6), latency_s=round(latency, 2), status=status,
            input_text=input_text if self.store_inputs else "[not stored]",
            output_text=output_text if self.store_inputs else "[not stored]",
        )

    def _raw(self, agent: str, messages: list[dict], schema: type[BaseModel] | None,
             model_override: str | None) -> LLMResponse:
        tier, effort = settings.AGENT_MODELS[agent]
        if model_override:
            tier = model_override
        model = settings.MODELS[tier]
        system = system_blocks(agent, schema)
        self._check_runaway()
        user_text = messages[-1]["content"]
        cap = settings.AGENT_MAX_TOKENS.get(agent, settings.MAX_TOKENS[tier])
        resp = self._send(agent, model, system, messages, effort, cap, user_text)
        ceiling = settings.RETRY_MAX_TOKENS[tier]
        if resp.truncated and ceiling > cap:
            # The reply was cut off at the default cap. Retry this call once with the higher
            # ceiling. The next call starts from the default again.
            resp = self._send(agent, model, system, messages, effort, ceiling, user_text)
        return resp

    def _send(self, agent, model, system, messages, effort, max_tokens, user_text) -> LLMResponse:
        self.steps += 1
        t0 = time.monotonic()
        try:
            resp = self.provider.complete(
                model=model, system=system, messages=messages,
                max_tokens=max_tokens, effort=effort,
                timeout=settings.CALL_TIMEOUT_SECONDS,
            )
        except LLMTimeout:
            self._log(agent, model, effort, None, 0.0, time.monotonic() - t0, "timeout", user_text, "")
            raise
        cost = compute_cost(model, resp.usage)
        self.cost += cost
        status = "truncated" if resp.truncated else "ok"
        self._log(agent, model, effort, resp.usage, cost, time.monotonic() - t0, status, user_text, resp.text)
        return resp

    def call(self, agent: str, user: str, schema: type[T] | None = None,
             compact_user: str | None = None, model_override: str | None = None) -> T | str:
        """Run one agent. Timeout: one retry with less context. Bad JSON: one repair attempt."""
        messages = [{"role": "user", "content": user}]
        try:
            resp = self._raw(agent, messages, schema, model_override)
        except LLMTimeout:
            smaller = compact_user or user[: max(2000, len(user) // 2)]
            messages = [{"role": "user", "content": smaller}]
            resp = self._raw(agent, messages, schema, model_override)

        if schema is None:
            return resp.text
        try:
            return schema.model_validate(extract_json(resp.text))
        except (ValueError, ValidationError) as first_error:
            repair = messages + [
                {"role": "assistant", "content": resp.text},
                {"role": "user", "content": (
                    "Your reply did not match the required JSON schema. Error:\n"
                    f"{str(first_error)[:1500]}\n\nReturn only the corrected JSON object."
                )},
            ]
            resp2 = self._raw(agent, repair, schema, model_override)
            try:
                return schema.model_validate(extract_json(resp2.text))
            except (ValueError, ValidationError) as second_error:
                raise AgentOutputError(f"{agent} output invalid after repair: {second_error}") from second_error


# --- fake provider for tests and offline demos -------------------------------------
class FakeProvider:
    """Returns scripted replies per agent. A reply can be a string, dict, or callable(messages)."""

    def __init__(self, replies: dict[str, Any], usage: Usage | None = None):
        self.replies = {k: (list(v) if isinstance(v, list) else v) for k, v in replies.items()}
        self.usage = usage or Usage(input_tokens=1000, output_tokens=300)
        self.calls: list[dict] = []

    def _agent_from_system(self, system: list[dict]) -> str:
        return system[-1].get("agent", "") if system else ""

    def complete(self, *, model, system, messages, max_tokens, effort, timeout) -> LLMResponse:
        agent = self._agent_from_system(system)
        self.calls.append({"agent": agent, "model": model, "messages": messages, "effort": effort})
        reply = self.replies.get(agent)
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(messages)
        if isinstance(reply, (dict, list)):
            reply = json.dumps(reply)
        if reply is None:
            raise KeyError(f"FakeProvider has no reply for agent '{agent}'")
        return LLMResponse(text=reply, usage=self.usage, model=model)
