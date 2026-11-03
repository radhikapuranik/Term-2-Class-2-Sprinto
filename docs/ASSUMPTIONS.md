# Assumptions to confirm with the instructor

Each item is a place where the brief left room for interpretation. The rule is in `icp.yaml` unless noted.

## ICP table
1. **Rows 3 and 5 overlap.** Row 3 is the prospect's own headcount (50 to 200). Row 5 reads "more than 50 clients, or more than 200 employees", which we take to mean the *clients* are large (over 200 employees), shown by enterprise logos. Both rows are implemented exactly as written. Please confirm this reading.
2. **"Retries" = number of sources tried.** Each row's retry number matches the number of places in its "where to look" column (row 1: 1, row 4: 3, and so on), so we read it as "try at most this many sources for this parameter". Unconfigured sources (Lusha with no key) are skipped without using a try.
3. **"Already shows all the certs" (row 4)** means both SOC 2 and ISO 27001 are claimed on the site (`required_certs`). Showing only some of them is "answered but not qualifying", so it goes to human review unless the careers page shows an audit or compliance job.
4. **Answered but not qualifying** (for example Series D, or 40 to 60 employees) is not an auto-reject, so hard rows (1 to 4) send the company to HUMAN REVIEW. Low-weight rows (5 to 7) never block a GO.
5. **System failures never auto-reject.** If a hard row is unanswered because Gemini was down, the page was blocked, or a JavaScript page could not be rendered, the company goes to HUMAN REVIEW with that reason, even for row 1 whose "if unanswered" says reject.
6. **"No certs found" needs a real page.** Row 4 only counts the absence of certs as a qualifying signal when the cleaned page has at least 300 characters. The code also scans for SOC 2 / ISO 27001 wording itself, so a badge Gemini misses can never read as "no certs".

## Sources and scraping
7. **Google News RSS is blocked by Google's robots.txt** (`Disallow: /` for all crawlers, `/rss` not allowed). Because the brief says to respect robots.txt, the news source tries Google News first, then falls back to **Bing News RSS** (allowed by Bing's robots.txt), then to the free GDELT news API. The source URL is stored for every answer.
8. **Footer handling.** The cleaner strips footers (layer 1) but first keeps footer lines and image alt text that mention keywords such as SOC 2 or GDPR, because cert badges usually live there and row 4 says to look in the footer.
9. **Fetch cap.** Every network request for a page or news feed counts toward the 8-fetch cap, including links that turn out to be 404. Cached pages do not count. Lusha and Hunter API calls are not page fetches.
10. **--refresh** re-researches a company but keeps paid API results (Hunter, Lusha) cached, so the free Hunter quota (25 searches a month) is never spent twice on one domain.
