# internship-scout

A bot that watches ~30 company career pages so you don't have to refresh Greenhouse all day everyday.

Every morning it checks ATS boards (Greenhouse, Ashby, workday), diffs against what you've already seen, and emails you only when something new drops.

## how it works

```
sources.yaml  →  fetch jobs  →  filter for "intern"  →  diff vs state.json  →  Gmail you
                                      ↑                        ↑
                              (not "international")    (the part that sometimes lies but god forbid u get reminded of an open role 2x)
```

1. **Fetch** — pulls open roles from each company's ATS API
2. **Filter** — keeps titles matching `intern`, `internship`, or `co-op`
3. **Diff** — compares job IDs against `state.json`; only unseen IDs trigger a notification
4. **Email** — one combined daily digest
5. **Commit state** — CI writes `state.json` back to the repo so the next run knows what's old news

Runs daily at 11:00 UTC via GitHub Actions. Because the best time to learn about a role is *after* 500 other people already applied.

## monitored companies

Jane Street, Stripe, Ramp, Anduril, Cloudflare, WorldQuant, Binance.US, and ~25 others. Full list in `sources.yaml`.

If your dream company uses Greenhouse, Ashby, or Workday, add them. If they use LinkedIn Easy Apply...

## setup

**Requirements:** Python 3.12+, and a Gmail account

```bash
pip install -r requirements.txt
python setup_gmail.py   # one-time OAuth for Gmail API
```

**Secrets** (for GitHub Actions):


| Secret              | What                     |
| ------------------- | ------------------------ |
| `GMAIL_CREDENTIALS` | OAuth client JSON        |
| `GMAIL_TOKEN`       | Refresh token from setup |
| `NOTIFY_EMAIL`      | Where to send alerts     |


**Run locally:**

```bash
python main.py
```

First run bootstraps `state.json` with every current intern role and sends a "system initialized" email. After that, only net-new postings ping you.

## project layout

```
adapters/       ATS fetchers (greenhouse, ashby, workday)
pipeline/       filter, diff, state management
notify/         Gmail sender
sources.yaml    companies to watch
state.json      what you've already seen (committed by CI)
main.py         orchestrator
```



## bumpy history

- **Duplicate emails:** historically caused by CI failing mid-run and not committing state. We fixed this. Probably. Maybe check your inbox anyway.
- **Workday sources:** occasionally return jobs without an `externalPath`. We skip those instead of crashing. Workday remains Workday.
- **Title renames:** if a company renames "University Grad" → "Software Engineer Intern", you'll get notified again. That's a feature if you're optimistic.
- **Closed roles vanish from state:** if a listing closes and reopens, it looks new. So does reposting with a fresh job ID. 

Want to add a company? Drop an entry in `sources.yaml`

