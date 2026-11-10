"""Document intake for Explore. Offline, using FakeProvider."""
import io
import json

import pypdf

import settings
from documents import extract_text
from llm import FakeProvider
from pipeline import handle_document

SCOPE_IN = json.dumps({"classification": "in_scope", "reason": "idea work"})
SCOPE_OUT = json.dumps({"classification": "out_of_scope", "reason": "not idea work"})
BRIEF = json.dumps({"summary": "A note on slow bus routes.", "key_points": ["Buses run late at peak"],
                    "problems": ["Riders wait too long"], "ideas_mentioned": ["Bus lanes"],
                    "open_questions": []})
EXPLORE = json.dumps({"problem": "Late buses", "coach_message": "Here are three ways.", "approaches": [],
                      "question": ""})


def _provider(scope=SCOPE_IN):
    return FakeProvider({"scope_gate": scope, "doc_reader": BRIEF, "explorer": EXPLORE})


def _agents(provider):
    return [c["agent"] for c in provider.calls]


# --- extraction --------------------------------------------------------------------
def test_reads_text_and_markdown():
    assert extract_text("notes.txt", b"hello world").text == "hello world"
    assert extract_text("NOTES.MD", b"# Title").ok


def test_rejects_unsupported_type_and_empty_file():
    assert not extract_text("slides.docx", b"x").ok
    assert not extract_text("empty.txt", b"   \n").ok


def test_rejects_files_over_the_size_limit(monkeypatch):
    monkeypatch.setattr(settings, "DOC_MAX_BYTES", 10)
    assert not extract_text("big.txt", b"x" * 11).ok


def test_long_text_is_cut_and_flagged(monkeypatch):
    monkeypatch.setattr(settings, "DOC_MAX_CHARS", 5)
    doc = extract_text("long.txt", b"abcdefghij")
    assert doc.ok and doc.truncated and doc.text == "abcde"


def test_pdf_without_text_is_reported_not_crashed():
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    doc = extract_text("blank.pdf", buf.getvalue())
    assert not doc.ok and "No readable text" in doc.message


# --- pipeline: gates and order -----------------------------------------------------------
def test_credential_in_document_blocks_everything(db):
    provider = _provider()
    sid = db.new_session("explore")
    result = handle_document(db, provider, sid, "keys.txt", "password: hunter2hunter2 is the admin login",
                             "", [])
    assert result.kind == "blocked"
    assert provider.calls == []  # nothing reached the API
    assert db.messages(sid) == []  # nothing saved


def test_out_of_scope_document_stops_before_the_full_text_is_read(db):
    provider = _provider(scope=SCOPE_OUT)
    sid = db.new_session("explore")
    result = handle_document(db, provider, sid, "a.txt", "Some document about bus routes.", "", [])
    assert result.kind == "rejected"
    assert _agents(provider) == ["scope_gate"]
    assert db.messages(sid) == []


def test_in_scope_document_is_read_then_explored(db):
    provider = _provider()
    sid = db.new_session("explore")
    result = handle_document(db, provider, sid, "a.txt", "Bus routes run late at peak hours.", "Focus on delays",
                             [])
    assert result.kind == "explore"
    assert _agents(provider) == ["scope_gate", "doc_reader", "explorer"]
    assert "Summary: A note on slow bus routes." in result.brief
    explorer_input = provider.calls[-1]["messages"][-1]["content"]
    assert "DOCUMENT BRIEF (a.txt" in explorer_input
    assert "MY LATEST MESSAGE:\nFocus on delays" in explorer_input


def test_scope_gate_sees_only_the_document_start(db, monkeypatch):
    monkeypatch.setattr(settings, "DOC_SCOPE_EXCERPT_CHARS", 20)
    provider = _provider()
    sid = db.new_session("explore")
    doc = "START OF DOC " + "filler " * 200 + "ENDMARKER"
    handle_document(db, provider, sid, "a.txt", doc, "", [])
    gate_input = provider.calls[0]["messages"][-1]["content"]
    reader_input = provider.calls[1]["messages"][-1]["content"]
    assert "START OF DOC" in gate_input and "ENDMARKER" not in gate_input
    assert "ENDMARKER" in reader_input


def test_later_turns_keep_the_brief(db):
    from pipeline import handle_explore_message

    provider = FakeProvider({"scope_gate": SCOPE_IN, "explorer": EXPLORE})
    sid = db.new_session("explore")
    handle_explore_message(db, provider, sid, "What about the late buses?", [], "", "BRIEF TEXT", "a.txt")
    explorer_input = provider.calls[-1]["messages"][-1]["content"]
    assert "DOCUMENT BRIEF (a.txt" in explorer_input and "BRIEF TEXT" in explorer_input
