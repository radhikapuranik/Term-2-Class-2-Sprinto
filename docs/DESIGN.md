# Outreach Desk: design notes

**Concept.** A calm mission control for one growth lead. In ten seconds it answers: which companies fit, why,
who do we write to, and what needs my review. Serious tool, warm voice, no template look.

**Architecture.** The Python core is unchanged. `outreach/api.py` is a thin FastAPI layer that calls the same
functions as the CLI (`qualify_company`, `draft_for`, `review`, `stats`) and serves `ui/` as plain HTML, CSS and
ES modules (no build step). GSAP 3.12.5 and the fonts come from `node_modules` and are served locally, so it works
offline. `python run_ui.py` installs them once, starts the server and opens the browser.

**Type.** Instrument Serif for headlines and hero numbers; Inter for text; JetBrains Mono for numbers, domains and
labels, with tabular numerals.

**Tokens** (`ui/assets/styles.css`, `:root`, light and dark, system default plus a toggle):

| Token | Light | Dark |
|---|---|---|
| paper / surface | #F7F6F2 / #FFFFFF | #0C0D14 / #151722 |
| ink / muted / hairline | #12131A / #5F6270 / #E4E2DA | #ECEDF5 / #9A9DB0 / #262938 |
| brand / highlight | #4F46E5 / #FFE066 | #8B85FF / #E6C34A |
| GO / NO-GO / HUMAN REVIEW / SENT | #12805C / #C2362F / #B7791F / #4F46E5 | #4FD1A1 / #FF8A80 / #F5B94B / #8B85FF |

Status is never colour alone: every chip has an icon and a word. Chip text uses slightly darker inks in light mode
for AA contrast. 8px spacing, 12-column grid, hairlines instead of heavy shadows, max width 1280px. The left rail
becomes a bottom bar under 760px; tables become stacked cards.

**Signature pieces.** Hero sentence with a hand-drawn highlighter; the funnel as one flowing SVG path; the ICP fit
ring (seven segments, reused in the table, detail header and review queue); the evidence ledger (quote with a
yellow sweep, source chip, copy); the agent loop timeline; the mail-composer card with the hook highlighted; the
edit % gauge; the test-mode ribbon on every page.

**Motion.** GSAP loads after the page is readable. Everything animates *from* its final visible state, only under
`prefers-reduced-motion: no-preference` (`gsap.matchMedia`), one easing family (expo/power out), under 0.8s.
Hero lines slide up, numbers count up once, the funnel draws, cards reveal on scroll, the ring morphs from the
table into the detail page (Flip), approve gives a small dot burst and a toast with an 8-second undo, reject
shakes and dims. Never animated: tables, the ribbon, form fields while typing.

**Pages.** `/` Overview · `/companies` · `/companies/:domain` · `/review` (J/K, A, E, X, U) · `/quality` · `/icp` ·
`/runs` · `/about` · a designed 404.

**Checks.** `tests/test_api.py` (endpoints and the recipient lock through the API), `tests/test_ui_e2e.py`
(headless click-through: run on 3 mocked domains, evidence, edit %, undo, dry run, reject, send, reduced motion,
keyboard). Lighthouse on the local app: Performance 92 to 93, Accessibility 100, Best Practices 100.
