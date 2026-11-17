# 90-second demo script

Before the demo: `.env.local` filled in, `uv run outreach run domains.txt` already run once (so it is cached),
and Outreach Desk open: `python run_ui.py` (it opens http://127.0.0.1:8600).

| Time | Do | Say |
|---|---|---|
| 0:00 | **Overview**: paste 5 domains into **Run the agent**, click **Run agent** | "Five domains in, one decision each, streamed live. Companies already researched come from the cache: zero new AI or Hunter calls." |
| 0:15 | **Companies** → filter **NO-GO** → open **Chargebee** | "Rejected because its security page already shows SOC 2 and ISO 27001. Here is the quote, highlighted, and the URL. It stopped early, so no tokens were wasted on the remaining rules." |
| 0:30 | **Companies** → open **Hevo** | "Seven rules, seven rows of evidence. SaaS, Series B from the news, an open Senior Compliance Engineer job. Headcount was unknown, so it went to human review, and I made the GO call and wrote down why." |
| 0:45 | **Review** → the Hevo draft | "Why this person: VP Engineering, the best title Hunter had. Two pain points tied to evidence. The highlighted hook is the real job post. The code checked every fact in the email." |
| 1:00 | Click **Approve and send** | "Test mode: it can only go to my own address, and I get 8 seconds to undo." |
| 1:10 | Show the email in my inbox (sent via Resend) | "Addressed to Amit by name, with a hook a human would answer." |
| 1:20 | **Quality** → the edit % gauge | "How much of each draft the reviewer changes. Over 50% means the automation isn't saving time. Opens aren't measured in test mode, and the page says so." |
