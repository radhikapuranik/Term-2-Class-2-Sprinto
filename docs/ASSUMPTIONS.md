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
11. **Bot-protected sites.** Some sites refuse automated readers (LeadSquared: HTTP 403, Zomato: timeout). We do not try to get around that. Once the homepage fails, the rest of that site is skipped and the company goes to HUMAN REVIEW.
12. **Menus are not content.** Many sites put a large menu in the HTML and load the real page with JavaScript (Chargebee's security page). The JavaScript detector measures text *after* menus, headers and footers are removed, then falls back to the browser.
13. **Certificates are combined across pages.** A cert seen on the security page still counts when the footer or careers page is checked next. Only the security page can prove "no certs". Pages that mention "our certifications" without naming them, or point to a gated trust portal, are treated as unanswered rather than "no certs". Cert badge images (for example `aicpa-logo.webp`, the SOC 2 logo) count as certs.

## Steps 4 to 7
14. **Human decision on HUMAN REVIEW.** HUMAN REVIEW means a person decides. The review page (or `outreach draft <domain> --reason ...`) records that decision and the reason separately from the agent's decision, so both stay visible. Hunter is only spent on GO companies.
15. **No Lusha key, so headcount is usually unanswered.** Row 3 looks at Lusha, About and Careers, and most About pages give no number. Without Lusha, most real companies land in HUMAN REVIEW on row 3. A Lusha key, or allowing news as a source for row 3, would change that.
16. **Contact title order** is in `outreach.yaml`: security, compliance or CISO first, then CTO, VP engineering, founder or CEO. Hunter is asked for senior and executive people only, and only the chosen person is stored.
17. **What the email may say about Sprinto.** `outreach.yaml` lists 7 facts copied from sprinto.com's homepage on 2026-11-03. sprinto.com blocks automated readers (HTTP 403), so the facts were read once in a normal browser. Any number or capitalised name in a draft that is not in the evidence or these facts fails validation.
18. **Shortlist (step 0) not built.** No Lusha key, and Google News blocks feed readers, so neither shortlist source is available. The system runs from `domains.txt`, as the brief allows.
19. **Edit %** is computed only on sent emails, over subject + body, as 1 minus difflib's similarity ratio. Rejected drafts are counted separately with their reason.
