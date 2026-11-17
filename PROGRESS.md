# Progress

## Done
- Phase 1: `icp.yaml`, SQLite cache, cleaner, JS detector, tests.
- Phase 2: polite fetcher + browser fallback, news (Bing RSS), capped agent loop, CLI. Live on 8 domains.
- Phase 3: Hunter contact (cached), pain points, validated email. Live draft for hevodata.com passed all checks.
- Phase 4: Streamlit review gate, send locked to TEST_RECIPIENT, edit % tile, `send --dry-run`.
- Phase 5: evidence page, README, docs/ASSUMPTIONS.md, docs/DEMO.md. Live checks: cache rerun = 0 new calls;
  SIMULATE_FAIL gemini/blocked/js/hunter all degrade to HUMAN REVIEW. 66 tests pass.

- Sender switched to Resend (HTML + text, id stored, errors -> HUMAN REVIEW). Gmail code removed.
- Real send of the Hevo draft through the review page: sent via Resend, edit 0%, Resend id stored.
  TEST_RECIPIENT is the Resend signup address (Resend's test sender only delivers there).
- Read-only snapshot on Vercel: https://sprinto-outreach-six.vercel.app (no keys, no send button, emails hidden).
  71 tests pass.

- Phase 6: `Sprinto_Outreach_Components_Map.xlsx` rebuilt in the course's component-map layout and colours
  (Component map, Steps in order, Where AI is used, Keys), matching the finished app.

## Next
- Optional: Lusha key (headcount), a verified domain in Resend (open tracking).
