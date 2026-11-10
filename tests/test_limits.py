"""Per-agent max_tokens and the per-run step limit. Offline, using FakeProvider."""
import settings
from llm import FakeProvider, RunContext
from pipeline import _research


class RecordingProvider(FakeProvider):
    def complete(self, **kwargs):
        self.max_tokens_seen = kwargs["max_tokens"]
        return super().complete(**kwargs)


def _ctx(db, provider):
    run_id = db.start_run("stress_test")
    return RunContext(db=db, provider=provider, run_id=run_id)


def test_agent_max_tokens_is_applied(db):
    provider = RecordingProvider({"doc_summarizer": "summary"})
    ctx = _ctx(db, provider)
    ctx.call("doc_summarizer", "some text")
    assert provider.max_tokens_seen == settings.AGENT_MAX_TOKENS["doc_summarizer"]


def test_agent_without_entry_falls_back_to_tier_default(db):
    provider = RecordingProvider({"doc_summarizer": "summary"})
    ctx = _ctx(db, provider)
    original = dict(settings.AGENT_MAX_TOKENS)
    settings.AGENT_MAX_TOKENS.pop("doc_summarizer")
    try:
        ctx.call("doc_summarizer", "some text")
    finally:
        settings.AGENT_MAX_TOKENS.update(original)
    tier, _ = settings.AGENT_MODELS["doc_summarizer"]
    assert provider.max_tokens_seen == settings.MAX_TOKENS[tier]


class TruncatingProvider(FakeProvider):
    """Cuts a reply off whenever the cap is below cut_below, like a real max_tokens stop."""

    def __init__(self, reply, cut_below):
        super().__init__({"doc_reader": reply})
        self.cut_below = cut_below
        self.caps: list[int] = []

    def complete(self, **kwargs):
        self.caps.append(kwargs["max_tokens"])
        resp = super().complete(**kwargs)
        resp.truncated = kwargs["max_tokens"] < self.cut_below
        return resp


def test_cut_off_reply_is_retried_once_at_the_higher_ceiling(db):
    provider = TruncatingProvider('{"ok": true}', cut_below=5000)
    ctx = _ctx(db, provider)
    text = ctx.call("doc_reader", "a long document")
    default = settings.AGENT_MAX_TOKENS["doc_reader"]
    tier, _ = settings.AGENT_MODELS["doc_reader"]
    assert provider.caps == [default, settings.RETRY_MAX_TOKENS[tier]]
    assert text == '{"ok": true}'
    assert ctx.steps == 2


def test_next_call_starts_from_the_default_again(db):
    provider = TruncatingProvider('{"ok": true}', cut_below=5000)
    ctx = _ctx(db, provider)
    ctx.call("doc_reader", "first")
    ctx.call("doc_reader", "second")
    default = settings.AGENT_MAX_TOKENS["doc_reader"]
    assert provider.caps[2] == default


def test_complete_reply_is_not_retried(db):
    provider = TruncatingProvider('{"ok": true}', cut_below=0)
    ctx = _ctx(db, provider)
    ctx.call("doc_reader", "short")
    assert len(provider.caps) == 1


def test_every_call_counts_as_a_step(db):
    provider = FakeProvider({"doc_summarizer": "summary"})
    ctx = _ctx(db, provider)
    ctx.call("doc_summarizer", "a")
    ctx.call("doc_summarizer", "b")
    assert ctx.steps == 2
    assert ctx.steps_left == settings.MAX_STEPS - 2


def test_research_is_skipped_when_steps_cannot_cover_it(db):
    provider = FakeProvider({})
    ctx = _ctx(db, provider)
    ctx.steps = settings.MAX_STEPS - (settings.STEPS_PER_RESEARCH + settings.FINAL_STEPS_RESERVE - 1)
    notes: list[str] = []
    _research(ctx, {"id": 1}, [{"id": 1}], notes.append)
    assert provider.calls == []  # no model call was made
    assert notes == ["Skipped research: step limit reached."]
