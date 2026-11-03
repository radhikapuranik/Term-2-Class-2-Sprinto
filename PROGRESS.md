# Progress

## Done
- Phase 1: project setup, `icp.yaml` (ICP table as data), SQLite schema + cache, 3-layer cleaner, JS-page detector, tests.
- Phase 2: polite fetcher (robots.txt, 1 req/s/host, Playwright fallback, login pages skipped), homepage link discovery,
  news (Google News -> Bing News RSS -> GDELT), Lusha (optional), Gemini extraction with schema + quote check,
  capped agent loop with short-circuit, GO / NO-GO / HUMAN REVIEW with evidence, CLI (`run`, `models`, `check-keys`).
  42 offline tests pass. Live fetching checked on chargebee.com and freshworks.com.

## Doing
- Checkpoint 1: waiting for GEMINI_API_KEY in .env.local, then `uv run outreach models` and a live run.

## Next
- Phase 3 (Hunter, pain points, email), Phase 4 (review gate, Gmail), Phase 5 (evidence page, docs, demo), Phase 6 (Excel sync:
  `Sprinto_Outreach_Components_Map.xlsx` is not in this folder; only `~/Downloads/PM_Developer_Assignment_Components_Map.xlsx` exists).
