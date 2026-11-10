"""Idea Coach: a personal, local tool that does only idea work.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import baseline
import db as dbmod
import devlog
import settings
from documents import SUPPORTED_TYPES, extract_text
from gates import security_filter
from pipeline import handle_document, handle_explore_message, run_stress_test
from prompts_loader import baseline_project_instructions, read_constraints
from research import get_searcher

st.set_page_config(page_title="Idea Coach", page_icon="💡", layout="wide")

STATUS_OPTIONS = ["captured", "exploring", "testing", "killed", "shipped"]
STATUS_LABELS = {
    "FACT": "🟢 FACT", "EVIDENCE_BASED_INFERENCE": "🔵 INFERENCE",
    "HYPOTHESIS": "🟡 HYPOTHESIS", "SPECULATION": "⚪ SPECULATION",
}


@st.cache_resource
def get_db() -> dbmod.DB:
    dbmod.backup()  # copy the database each time the app starts
    return dbmod.DB()


@st.cache_resource
def get_provider():
    from llm import AnthropicProvider
    return AnthropicProvider()


db = get_db()
keys_ok = bool(settings.ANTHROPIC_API_KEY)


def update_docs() -> None:
    """Keep CHANGELOG.md and ROADMAP.md current; never interrupts the app."""
    devlog.safe_sync(db, get_provider() if keys_ok else None)


@st.cache_resource
def docs_synced_at_startup() -> bool:
    update_docs()  # records any code, prompt, or setting change since the last start
    return True


docs_synced_at_startup()

# --- sidebar --------------------------------------------------------------------
st.sidebar.title("💡 Idea Coach")
page = st.sidebar.radio("Page", ["Explore", "Ideas", "Baseline", "Runs & costs", "Constraints"],
                        label_visibility="collapsed")
total = db.one("SELECT COALESCE(SUM(total_cost), 0) AS c FROM runs")["c"]
month = db.one("SELECT COALESCE(SUM(total_cost), 0) AS c FROM runs "
               "WHERE started_at >= date('now', 'start of month')")["c"]
st.sidebar.caption(f"Spend this month: ${month:.2f} · all time: ${total:.2f}")
if not keys_ok:
    st.sidebar.error("ANTHROPIC_API_KEY is missing. Add it to .env and restart.")
if not settings.TAVILY_API_KEY:
    st.sidebar.warning("TAVILY_API_KEY is missing. Stress Test needs it.")


# =============================================================================
# Explore
# =============================================================================
def page_explore() -> None:
    st.header("Explore")
    st.caption("Describe a problem, frustration, or rough idea. Explore suggests up to three different "
               "approaches; keep the ones worth stress-testing.")
    ss = st.session_state
    if "session_id" not in ss:
        ss.session_id = db.new_session("explore")
        ss.chat = []          # what the screen shows, including blocked and rejected turns
        ss.pending_q = ""
        ss.kept = set()
        ss.doc_brief = ""     # brief of the uploaded document, used by later turns in this session
        ss.doc_name = ""

    if st.button("New session"):
        for k in ("session_id", "chat", "pending_q", "kept", "doc_brief", "doc_name"):
            ss.pop(k, None)
        st.rerun()

    for i, turn in enumerate(ss.chat):
        with st.chat_message(turn["role"]):
            st.markdown(turn["text"])
            out = turn.get("explore")
            if out:
                if out.problem:
                    st.markdown(f"**Underlying problem:** {out.problem}")
                for j, a in enumerate(out.approaches):
                    with st.container(border=True):
                        st.markdown(f"**{a.title}** · {STATUS_LABELS[a.epistemic_status]}")
                        st.markdown(a.description)
                        st.markdown(f"*Changes the assumption:* {a.assumption_changed}")
                        st.markdown(f"*Why it might work:* {a.why_it_might_work}")
                        if a.disadvantages:
                            st.markdown("*Disadvantages:* " + "; ".join(a.disadvantages))
                        if a.constraints_note:
                            st.caption(f"Constraints: {a.constraints_note}")
                        key = f"{i}-{j}"
                        if key in ss.kept:
                            st.success("Kept as an idea")
                        elif st.button("Keep this idea", key=f"keep-{key}"):
                            db.add_idea(a.title, a.description, problem=out.problem,
                                        assumption_changed=a.assumption_changed, session_id=ss.session_id)
                            ss.kept.add(key)
                            st.rerun()
                if out.question:
                    st.info(out.question)

    if not keys_ok:
        st.stop()

    with st.expander("Add a document (optional)"):
        upload = st.file_uploader(
            f"Upload a file ({', '.join(t for t in SUPPORTED_TYPES)}, up to 5 MB)",
            type=SUPPORTED_TYPES, key=f"upload-{ss.session_id}",
        )
        focus = st.text_input("What should Explore focus on? (optional)", key=f"focus-{ss.session_id}")
        if upload is not None and st.button("Read document and explore", key=f"read-{ss.session_id}"):
            doc = extract_text(upload.name, upload.getvalue())
            if not doc.ok:
                st.error(doc.message)
            else:
                with st.spinner("Reading the document..."):
                    result = handle_document(db, get_provider(), ss.session_id, upload.name, doc.text,
                                             focus, db.messages(ss.session_id))
                label = f"📄 {upload.name}: {focus.strip() or 'Explore the ideas in this document.'}"
                if doc.truncated:
                    label += f" (only the first {settings.DOC_MAX_CHARS:,} characters were read)"
                if result.kind == "blocked":
                    ss.chat.append({"role": "assistant", "text": f"🔒 {result.text}"})
                else:
                    ss.chat.append({"role": "user", "text": label})
                    ss.chat.append({"role": "assistant", "text": result.text, "explore": result.explore})
                    if result.brief:
                        ss.doc_brief, ss.doc_name = result.brief, upload.name
                ss.pending_q = ""
                st.rerun()

    message = st.chat_input("What problem or idea are you thinking about?")
    if message:
        history = db.messages(ss.session_id)
        with st.spinner("Thinking..."):
            result = handle_explore_message(db, get_provider(), ss.session_id, message, history, ss.pending_q,
                                            ss.doc_brief, ss.doc_name)
        if result.kind == "blocked":
            ss.chat.append({"role": "assistant", "text": f"🔒 {result.text}"})
        else:
            ss.chat.append({"role": "user", "text": message})
            ss.chat.append({"role": "assistant", "text": result.text, "explore": result.explore})
        ss.pending_q = result.text if result.kind == "clarify" else ""
        st.rerun()


# =============================================================================
# Ideas
# =============================================================================
def render_result(result: dict) -> None:
    ev = result["evaluator"]
    st.markdown(f"#### Surviving concept\n{result['surviving_concept']}")
    st.markdown(result["summary"])
    if not result.get("still_addresses_problem", True):
        st.warning("The surviving concept no longer fully addresses the original problem.")

    st.markdown("#### Claims")
    for c in result["claims"]:
        crit = "**critical** · " if c["critical"] else ""
        with st.expander(f"{STATUS_LABELS[c['status']]} · {c['text'][:110]}"):
            st.markdown(f"{crit}{c['text']}")
            if not c["evidence"]:
                st.caption("No evidence recorded.")
            for e in c["evidence"]:
                st.markdown(f"- {e['direction']} · verification: **{e['verification']}** · "
                            f"[{e['title'] or e['url']}]({e['url']})  \n  {e['summary']}")

    st.markdown("#### Unresolved blockers")
    if result["unresolved_blockers"]:
        for b in result["unresolved_blockers"]:
            st.error(b)
    else:
        st.markdown("None reported.")
    if result.get("unvalidated_critical_claims"):
        st.caption("Unvalidated critical claims: " + " · ".join(result["unvalidated_critical_claims"]))

    st.markdown(f"#### Distinctive value lost\n{result['distinctive_value_lost']}")
    st.markdown("#### Smallest test (within a week)")
    st.info(result["smallest_test"])
    c1, c2 = st.columns(2)
    c1.markdown(f"**Success:** {result['success_criteria']}")
    c2.markdown(f"**Failure:** {result['failure_criteria']}")
    st.caption(f"Cost ${result['cost_usd']:.3f} · {result['searches']} searches · {result['duration_s']}s")

    with st.expander("Evaluator reasoning", expanded=False):
        st.markdown(f"**Verdict:** `{ev['verdict']}` (history: {' → '.join(ev['history'])})")
        for r in ev["reasons"]:
            st.markdown(f"- {r}")
        if ev.get("objections"):
            st.markdown("**Objections**")
            for o in ev["objections"]["objections"]:
                st.markdown(f"- **{o['id']}** {o['objection']} — {o['why_it_matters']}")
        if ev.get("counter"):
            st.markdown("**Counter-assessments**")
            for a in ev["counter"]["assessments"]:
                st.markdown(f"- **{a['objection_id']}** ({a['strength']}) {a['revised_interpretation']}")
        if result.get("log"):
            st.markdown("**Run log**")
            st.code("\n".join(result["log"]))


def stress_test_button(idea: dict) -> None:
    ss = st.session_state
    paused_key = f"paused-{idea['id']}"
    if ss.get(paused_key):
        st.warning(ss[paused_key] + " Continue anyway? The run starts again with the pause lifted.")
        go = st.button("Continue anyway", key=f"cont-{idea['id']}")
        allow = True
    else:
        go = st.button("Stress test this", type="primary", key=f"st-{idea['id']}",
                       disabled=not (keys_ok and settings.TAVILY_API_KEY))
        allow = False
    if not go:
        return
    status = st.status("Running Stress Test...", expanded=True)
    outcome = run_stress_test(db, get_provider(), get_searcher(), idea["id"], allow_runaway=allow,
                              progress=lambda m: status.write(m))
    ss.pop(paused_key, None)
    update_docs()
    if outcome.status == "ok":
        status.update(label=f"Done · ${outcome.cost:.3f}", state="complete", expanded=False)
        st.rerun()
    elif outcome.status == "paused":
        status.update(label="Paused", state="error")
        ss[paused_key] = outcome.message
        st.rerun()
    else:
        status.update(label="Failed", state="error")
        st.error(outcome.message)


def baseline_section(idea: dict, results: list[dict]) -> None:
    st.markdown("#### Baseline comparison")
    comps = db.all("SELECT * FROM baseline_comparisons WHERE idea_id = ? ORDER BY id DESC", (idea["id"],))
    open_comp = next((c for c in comps if c["winner"] is None), None)
    if open_comp:
        res = next((r["result"] for r in results if r["id"] == open_comp["stress_result_id"]), None)
        if res is None:
            st.caption("The Stress Test result for this comparison is missing.")
            return
        proto = baseline.result_markdown(res)
        a, b = (proto, open_comp["project_output"]) if open_comp["prototype_label"] == "A" \
            else (open_comp["project_output"], proto)
        st.caption("Score blind. The labels are random and revealed after you submit.")
        ca, cb = st.columns(2)
        with ca.container(border=True):
            st.markdown("### A")
            st.markdown(a)
        with cb.container(border=True):
            st.markdown("### B")
            st.markdown(b)
        with st.form(f"score-{open_comp['id']}"):
            winner = st.radio("Which helped you more?", ["A", "B", "tie"], horizontal=True)
            changed = st.checkbox("The winner changed what I decided to do")
            flaw = st.checkbox("The winner caught a real flaw the other missed")
            notes = st.text_input("Notes (optional)")
            if st.form_submit_button("Submit score"):
                baseline.score(db, open_comp["id"], winner, changed, flaw, notes)
                update_docs()
                who = "the prototype" if winner == open_comp["prototype_label"] else (
                    "a tie" if winner == "tie" else "the Claude Project")
                st.success(f"Recorded. The prototype was {open_comp['prototype_label']}; you picked {who}.")
        return
    if not results:
        st.caption("Run a Stress Test first.")
        return
    with st.form(f"newcomp-{idea['id']}"):
        st.caption("Paste the Claude Project's answer for this same idea (instructions are on the Baseline page).")
        pasted = st.text_area("Claude Project output", height=180)
        if st.form_submit_button("Create blind comparison") and pasted.strip():
            fr = security_filter(pasted)
            if fr.blocked:
                st.error(fr.message)
            else:
                baseline.create(db, idea["id"], results[0]["id"], pasted.strip())
                st.rerun()


def page_ideas() -> None:
    st.header("Ideas")
    with st.expander("Add your own idea"):
        with st.form("add-idea", clear_on_submit=True):
            title = st.text_input("Title")
            desc = st.text_area("Idea")
            problem = st.text_area("Problem it solves (optional)")
            if st.form_submit_button("Save idea") and title.strip() and desc.strip():
                fr = security_filter(" ".join((title, desc, problem)))
                if fr.blocked:
                    st.error(fr.message)
                else:
                    db.add_idea(title.strip(), desc.strip(), problem=problem.strip())
                    st.rerun()

    ideas = db.ideas()
    if not ideas:
        st.info("No ideas yet. Keep one from Explore or add your own above.")
        return
    status_filter = st.multiselect("Status", STATUS_OPTIONS, default=["captured", "exploring", "testing"])
    shown = [i for i in ideas if i["status"] in status_filter]
    if not shown:
        st.caption("No ideas with that status.")
        return
    labels = {f"#{i['id']} · {i['title']} ({i['status']})": i["id"] for i in shown}
    choice = st.selectbox("Idea", list(labels))
    idea = db.get_idea(labels[choice])

    st.subheader(idea["title"])
    st.markdown(idea["description"])
    if idea["problem"]:
        st.caption(f"Problem: {idea['problem']}")

    c1, c2, c3 = st.columns([1, 1, 2])
    new_status = c1.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(idea["status"]))
    new_stage = c2.selectbox("Stage", ["early", "later"], index=["early", "later"].index(idea["stage"]),
                             help="Early: is this worth testing? Later: is this ready to pursue?")
    kill_reason = c3.text_input("Reason (required to kill)", value=idea["kill_reason"] or "")
    if (new_status, new_stage, kill_reason) != (idea["status"], idea["stage"], idea["kill_reason"] or ""):
        if new_status == "killed" and not kill_reason.strip():
            st.warning("Add a reason before killing an idea; it becomes a Lesson later.")
        else:
            db.update_idea(idea["id"], status=new_status, stage=new_stage, kill_reason=kill_reason.strip() or None)
            st.rerun()

    stress_test_button(idea)
    results = db.stress_results(idea["id"])
    tabs = st.tabs(["Latest result", "Claim ledger", "History", "Baseline"])
    with tabs[0]:
        if results:
            render_result(results[0]["result"])
        else:
            st.caption("No Stress Test yet.")
    with tabs[1]:
        claims = db.claims(idea["id"])
        if not claims:
            st.caption("Claims appear after the first Stress Test.")
        for c in claims:
            with st.expander(f"C{c['id']} · {STATUS_LABELS[c['status']]} · {c['text'][:100]}"):
                for e in db.claim_events(c["id"]):
                    attempted = f" (requested {e['attempted_status']})" if e["attempted_status"] else ""
                    st.markdown(f"- {e['created_at']}: {e['from_status'] or '—'} → **{e['to_status']}**"
                                f"{attempted} · {e['cause']}")
    with tabs[2]:
        for r in results:
            res = r["result"]
            st.markdown(f"- {r['created_at']} · `{res['evaluator']['verdict']}` · ${res['cost_usd']:.3f}")
    with tabs[3]:
        baseline_section(idea, results)


# =============================================================================
# Baseline
# =============================================================================
def page_baseline() -> None:
    st.header("Baseline comparison")
    s = baseline.summary(db)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ideas scored", f"{s['ideas']} / {baseline.PASS_IDEAS}")
    c2.metric("Prototype wins", f"{s['prototype_wins']} (need {baseline.PASS_WINS})")
    c3.metric("Changed a decision or caught a flaw", f"{s['impact']} (need {baseline.PASS_IMPACT})")
    c4.metric("Ties", s["ties"])
    if s["complete"]:
        (st.success if s["passed"] else st.error)(
            "Passed: build Phase 4." if s["passed"] else
            "Did not pass: keep the Claude Project and build only the claim ledger and experiment log.")
    else:
        st.info("Score your next 10 real ideas before deciding on Phase 4.")
    st.markdown("**How to run it:** create a Claude Project, paste the instructions below as its "
                "custom instructions, and give it the same idea you stress-test here. Then paste its answer on "
                "the idea's Baseline tab.")
    text = baseline_project_instructions()
    st.download_button("Download Claude Project instructions", text, file_name="claude_project_instructions.md")
    with st.expander("Preview instructions"):
        st.code(text, language="markdown")


# =============================================================================
# Runs & costs
# =============================================================================
def page_runs() -> None:
    st.header("Runs & costs")
    runs = db.all("SELECT * FROM runs ORDER BY id DESC LIMIT 200")
    if not runs:
        st.caption("No runs yet.")
        return
    df = pd.DataFrame(runs)
    st_runs = df[df["mode"] == "stress_test"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Stress Tests", len(st_runs))
    c2.metric("Avg Stress Test cost", f"${st_runs['total_cost'].mean():.3f}" if len(st_runs) else "—")
    c3.metric("Avg Stress Test time", f"{st_runs['duration_s'].mean():.0f}s" if len(st_runs) else "—")

    verdicts = st_runs["verdict"].dropna().value_counts()
    if len(verdicts):
        st.markdown("**Verdict distribution** (if one verdict dominates real ideas, retune the bars)")
        st.bar_chart(verdicts)

    st.dataframe(df[["id", "mode", "idea_id", "status", "verdict", "total_cost", "search_count",
                     "duration_s", "prompt_version", "started_at", "notes"]],
                 hide_index=True, width="stretch")
    run_id = st.number_input("Inspect run", min_value=1, value=int(runs[0]["id"]), step=1)
    calls = db.all("SELECT agent, model, effort, input_tokens, output_tokens, cache_read_tokens, cost, "
                   "latency_s, status FROM llm_calls WHERE run_id = ? ORDER BY id", (int(run_id),))
    if calls:
        st.dataframe(pd.DataFrame(calls), hide_index=True, width="stretch")
        by_agent = pd.DataFrame(calls).groupby("agent")["cost"].sum().sort_values(ascending=False)
        st.caption("Cost by agent: " + " · ".join(f"{a} ${c:.4f}" for a, c in by_agent.items()))


# =============================================================================
# Constraints
# =============================================================================
def page_constraints() -> None:
    st.header("Constraints")
    st.caption("You write this file; nothing here is inferred. The Explorer, Evaluator, and Coach read it.")
    text = st.text_area("constraints.md", value=read_constraints(), height=400)
    if st.button("Save"):
        fr = security_filter(text)
        if fr.blocked:
            st.error(fr.message)
        else:
            settings.CONSTRAINTS_PATH.write_text(text, encoding="utf-8")
            st.success("Saved.")


{"Explore": page_explore, "Ideas": page_ideas, "Baseline": page_baseline,
 "Runs & costs": page_runs, "Constraints": page_constraints}[page]()
