# 90-second demo script

Before the demo: `.env.local` filled in, `uv run outreach run domains.txt` already run once (so it is cached),
and the review page open: `uv run streamlit run app.py`.

| Time | Do | Say |
|---|---|---|
| 0:00 | In the terminal: `uv run outreach run domains.txt` | "Five-plus domains in, one decision each. The second run is instant: everything is cached, zero new AI or Hunter calls." |
| 0:15 | Review page → **Runs and evidence** → open **chargebee.com: NO-GO** | "Rejected because its security page already shows SOC 2 and ISO 27001. Here is the quote and the URL. It stopped there, so no tokens were wasted on the remaining rows." |
| 0:30 | Open **hevodata.com** | "Qualified on SaaS, Series B from news, and an open Senior Compliance Engineer job. Every row has a source URL and a quote. Headcount was unknown, so the table sent it to human review, and I made the GO call and wrote down why." |
| 0:45 | **Review gate** tab → the Hevo draft | "Why this person: VP Engineering, the best title Hunter had. Two pain points, each tied to evidence. The hook is the real job post. The code checked that every fact in the email is in the evidence." |
| 1:00 | Click **Approve and send** | "Test mode: it can only go to my own address. The code refuses any other recipient." |
| 1:10 | Show the email in Gmail | "Addressed to Amit by name, with a hook a human would answer." |
| 1:20 | Point to the **Average edit %** tile | "This tracks how much of each draft the reviewer changes. Above 50% turns red, which would mean the automation is not saving time." |
