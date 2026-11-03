# Sprinto cold outreach agent

Give it a list of company domains. For each one it researches the website and news, qualifies the
company against Sprinto's ICP (`icp.yaml`), finds the right person (Hunter.io), names two
evidence-backed pain points, drafts a short personal email, and waits for a human to approve it.
Every email goes only to your own address (`TEST_RECIPIENT`).

## Run it

```bash
uv run outreach check-keys                # test every key in .env.local
uv run outreach run domains.txt           # steps 1-6 for every domain (cached; add --refresh to redo)
uv run streamlit run app.py               # review gate + runs and evidence page (http://localhost:8501)
uv run outreach draft acme.com --reason "why a human says GO"   # steps 4-6 for a HUMAN REVIEW company
uv run outreach send acme.com --dry-run   # print the approved email instead of sending
uv run pytest                             # 66 offline tests, no keys or network needed
```

Failure drills: `SIMULATE_FAIL=gemini` (or `hunter`, `blocked`, `js`, comma-separated) before any command.

## How a decision is made

| Step | File | What happens |
|---|---|---|
| 1 Scrape | `outreach/fetcher.py` | robots.txt respected, 1 request/second/host, plain HTML first, Playwright only when the page body is empty (JavaScript-only). Login pages and LinkedIn are never fetched. Every page is cached. |
| 2 Extract | `outreach/cleaner.py`, `agent.py` | 3-layer cleaning (rules, keyword heuristics, ~7,000-token cap). Gemini writes a one-line profile. |
| 3 Qualify | `outreach/agent.py`, `icp.py`, `icp.yaml` | For each open ICP row, in table order, fetch the next "where to look" source, ask Gemini that one question (JSON schema, quote must be on the page), apply the row's rule in code. Stops on a reject, on retry limits, 8 fetches or 60 seconds. Result: GO / NO-GO / HUMAN REVIEW with a quote and URL per row. |
| 4 Contact | `outreach/contact.py`, `outreach.yaml` | Hunter Domain Search (cached forever), best title: security/compliance/CISO, then CTO, VP engineering, founder/CEO. Only that person's work name, title and email are kept. |
| 5-6 Pains and email | `outreach/writer.py` | Two pain points, each citing evidence. Email under 120 words, subject under 8 words, checked for name, hook, placeholders and any number or name not in the evidence. 2 retries, then HUMAN REVIEW. |
| 7 Review and send | `app.py`, `outreach/send.py` | Approve / Edit / Reject. Gmail SMTP, hard-locked to `TEST_RECIPIENT`. Edit % tracked (red above 50%). |

Gemini (`GEMINI_MODEL`, chosen by `uv run outreach models`) never decides GO or NO-GO: it only extracts, explains and writes.
Data lives in `data/outreach.db` (SQLite). Rule readings to confirm are in `docs/ASSUMPTIONS.md`; the demo is in `docs/DEMO.md`.
