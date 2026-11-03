"""Local review gate and evidence page. Run: uv run streamlit run app.py"""
import json

import pandas as pd
import streamlit as st

from outreach import db
from outreach.contact import load_rules
from outreach.llm import Gemini
from outreach.send import RecipientLocked, review, stats
from outreach.writer import draft_for

st.set_page_config(page_title="Sprinto Outreach", layout="wide")
con = db.connect()

st.warning("Test mode: every email goes to my own address (TEST_RECIPIENT). Prospects never receive anything.")
dry_run = st.sidebar.checkbox("Dry run (print instead of sending)", value=False)

s = stats(con)
c1, c2, c3 = st.columns(3)
c1.metric("Emails sent", s["sent"])
c2.metric("Open rate", "n/a", help=s["open_rate"])
with c3:
    color = "red" if s["avg_edit_pct"] > 50 else "green"
    st.markdown(f"**Average edit %** (goal under 50%)<br><span style='font-size:2rem;color:{color}'>"
                f"{s['avg_edit_pct']}%</span>", unsafe_allow_html=True)
    if s["avg_edit_pct"] > 50:
        st.error("Reviewers change more than half of each draft: the automation is not saving time yet.")


def answers_table(domain):
    rows = con.execute("SELECT param_id, outcome, reason, evidence_quote, source_url, attempts FROM answers "
                       "WHERE domain=?", (domain,)).fetchall()
    return pd.DataFrame([dict(r) for r in rows])


review_tab, evidence_tab = st.tabs(["Review gate", "Runs and evidence"])

# --- Review gate ---------------------------------------------------------------
with review_tab:
    companies = [dict(r) for r in con.execute("SELECT * FROM companies ORDER BY processed_at DESC")]
    pending = [c for c in companies if c["decision"] == "HUMAN REVIEW" and db.effective_decision(con, c["domain"]) == "HUMAN REVIEW"]
    if pending:
        st.subheader(f"Needs a human decision ({len(pending)})")
    for c in pending:
        with st.expander(f"{c['domain']}: HUMAN REVIEW"):
            for r in json.loads(c["reasons_json"]):
                st.write("- " + r)
            st.dataframe(answers_table(c["domain"]), hide_index=True)
            why = st.text_input("Your reason", key=f"why-{c['domain']}")
            a, b = st.columns(2)
            if a.button("Mark GO and draft email", key=f"go-{c['domain']}", disabled=not why):
                db.set_override(con, c["domain"], "GO", why)
                with st.spinner("Finding the contact and writing the draft..."):
                    draft_for(con, c["domain"], Gemini(con), load_rules())
                st.rerun()
            if b.button("Mark NO-GO", key=f"nogo-{c['domain']}", disabled=not why):
                db.set_override(con, c["domain"], "NO-GO", why)
                st.rerun()

    drafts = [dict(r) for r in con.execute("SELECT * FROM drafts WHERE status IN ('draft','human_review') ORDER BY created_at")]
    st.subheader(f"Drafts to review ({len(drafts)})")
    if not drafts:
        st.info("No drafts waiting. Run `uv run outreach run domains.txt`, or mark a company GO above.")
    for d in drafts:
        dom = d["domain"]
        contact = json.loads(d["contact_json"] or "null") or {}
        comp = db.cached_company(con, dom) or {}
        st.markdown(f"### {comp.get('name') or dom} ({dom})")
        if d["status"] == "human_review":
            st.error(f"Needs attention: {d['notes']}")
        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Why this company qualified**")
            override = con.execute("SELECT decision, reason FROM overrides WHERE domain=?", (dom,)).fetchone()
            st.write(f"Agent decision: **{comp.get('decision')}**"
                     + (f". Human decision: **{override[0]}** ({override[1]})" if override else ""))
            st.dataframe(answers_table(dom), hide_index=True)
            if contact:
                st.markdown(f"**Why this person:** {contact['first_name']} {contact['last_name']}, {contact['title']} "
                            f"({contact['email']}). {contact['why']}. Source: {contact['source']}.")
            for i, p in enumerate(json.loads(d["pains_json"] or "[]"), 1):
                st.markdown(f"**Pain point {i}:** {p['pain']}  \n_Why it matters to them:_ "
                            f"{p['why_it_matters_to_this_role']}  \n_Evidence:_ \"{p['evidence_quote']}\" ({p['url']})")
        with right:
            st.markdown(f"**Draft** (hook: \"{d['hook']}\")")
            subj = st.text_input("Subject", d["subject"] or "", key=f"s-{dom}")
            body = st.text_area("Body", d["body"] or "", height=300, key=f"b-{dom}")
            reason = st.text_input("Reject reason", key=f"r-{dom}")
            a, b, c = st.columns(3)
            try:
                if a.button("Approve and send", key=f"ok-{dom}", disabled=not d["body"]):
                    st.success(f"Approved: {review(con, dom, 'approved', dry_run=dry_run)}")
                    st.rerun()
                if b.button("Edit and send", key=f"ed-{dom}", disabled=not body):
                    st.success(f"Edited: {review(con, dom, 'edited', subj, body, dry_run=dry_run)}")
                    st.rerun()
                if c.button("Reject", key=f"no-{dom}", disabled=not reason):
                    review(con, dom, "rejected", reason=reason)
                    st.rerun()
            except (RecipientLocked, RuntimeError, OSError) as e:
                st.error(f"Not sent: {e}")
        st.divider()

    done = [dict(r) for r in con.execute("SELECT domain, status, review_action, edit_ratio, final_subject, reject_reason "
                                         "FROM drafts WHERE status IN ('sent','rejected')")]
    if done:
        st.subheader("Reviewed")
        st.dataframe(pd.DataFrame(done), hide_index=True)

# --- Runs and evidence -----------------------------------------------------------
with evidence_tab:
    rows = []
    for c in companies:
        dom = c["domain"]
        tok = con.execute("SELECT COUNT(*), COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0) FROM llm_calls "
                          "WHERE domain=?", (dom,)).fetchone()
        meth = dict(con.execute("SELECT method, COUNT(*) FROM pages WHERE domain=? GROUP BY method", (dom,)).fetchall())
        rows.append({"domain": dom, "decision": c["decision"], "human": db.effective_decision(con, dom),
                     "seconds": c["elapsed_s"], "gemini calls": tok[0], "tokens in": tok[1], "tokens out": tok[2],
                     "html pages": meth.get("http", 0), "browser pages": meth.get("browser", 0),
                     "news feeds": meth.get("rss", 0),
                     "fetch cost units": meth.get("http", 0) + meth.get("rss", 0) + 12 * meth.get("browser", 0),
                     "stopped because": c["stop_reason"]})
    st.caption("Fetch cost units: plain HTML or news = 1, browser (Playwright) page = 12 (10 to 15 times more).")
    st.dataframe(pd.DataFrame(rows), hide_index=True)
    for c in companies:
        with st.expander(f"{c['domain']}: {c['decision']}"):
            for r in json.loads(c["reasons_json"]):
                st.write("- " + r)
            st.dataframe(answers_table(c["domain"]), hide_index=True)
            log = con.execute("SELECT datetime(ts,'unixepoch','localtime') AS time, event FROM loop_log WHERE domain=? "
                              "ORDER BY id DESC LIMIT 40", (c["domain"],)).fetchall()
            st.dataframe(pd.DataFrame([dict(r) for r in log]), hide_index=True)
