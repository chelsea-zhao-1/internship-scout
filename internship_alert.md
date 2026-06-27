# Internship Role Monitor — Project Specification

## 1. Overview

### 1.1 Problem

Internship postings at top companies appear without warning and fill quickly. The earlier you apply, the better your chances. There is currently no reliable way to get notified the moment a new intern role opens at a specific company without manually checking careers pages.

### 1.2 Solution

An automated daily pipeline that monitors job postings at target companies, detects new intern roles, and sends a morning email digest to the user's personal Gmail. The system should run with zero manual intervention after initial setup.

### 1.3 Success Criteria

- The user receives a daily morning email by ~8:00 AM ET.
- If new intern roles have appeared since the last check, each one is listed with title, location, and a direct apply link.
- If no new roles exist, the email confirms the system ran successfully ("No new intern roles today").
- The system runs reliably via GitHub Actions with no self-hosted infrastructure.
- The system is maintainable and extensible to additional companies in the future.

### 1.4 Project Phases

- **Project A (current scope):** Monitor a fixed list of known target companies. Coinbase is the first and only company for initial implementation.
- **Project B (future):** Discovery pipeline for finding lesser-known companies. Project B will feed into Project A's infrastructure.

---

## 2. Architecture

### 2.1 High-Level Pipeline

```
┌───────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│   FETCH   │───▶│  NORMALIZE  │───▶│  FILTER  │───▶│   DIFF   │───▶│  NOTIFY  │
│ (sources) │    │ (canonical) │    │ (intern?)│    │(new only)│    │ (email)  │
└───────────┘    └─────────────┘    └──────────┘    └──────────┘    └──────────┘
                                                         │
                                                   ┌─────┴─────┐
                                                   │   STATE   │
                                                   │  STORE    │
                                                   │(JSON/git) │
                                                   └───────────┘
```

Each stage is separated by its axis of change. The fetch layer handles source-specific API calls. The normalizer converts vendor-specific shapes into a canonical schema. The filter applies user criteria. The diff compares against stored state. The notifier composes and sends the email. Each layer is independently swappable.

### 2.2 Design Principles

- **Config-driven source registry:** Companies and their ATS details are declared in a config file (`sources.yaml`), not hardcoded in application logic.
- **Normalization at the boundary:** Each ATS adapter translates vendor-specific JSON into a canonical `Job` schema. This is O(N) translators per ATS, not O(N×M) point-to-point integrations.
- **Stages separated by axis of change:** Fetching, filtering, diffing, and notifying change for different reasons and at different rates. Keeping them isolated means changes to one don't cascade.
- **Polling over push:** We don't control the data source, so polling is the correct pattern.
- **JSON file in git as state store:** Appropriate at this scale. A database adds unnecessary operational overhead for tracking ~10–50 roles across one company.
- **State updates only after successful notification:** The pipeline must not mark roles as "seen" until the email has been confirmed sent. This prevents silent data loss.

---

## 3. Data Model

### 3.1 Canonical Job Schema

Every job from every source is normalized into this shape before entering the filter/diff stages:

```json
{
  "id": "string — unique identifier from the ATS (e.g., Greenhouse job ID)",
  "title": "string — job title as posted",
  "location": "string — e.g., 'Remote - USA', 'New York, NY'",
  "url": "string — direct link to the job posting / application page",
  "updated_at": "string — ISO 8601 timestamp of last update from the ATS",
  "source": "string — identifier for the company/board (e.g., 'coinbase', 'cdpjobs')"
}
```

### 3.2 State File Schema

The state file (`state.json`) is stored in the git repository and committed after each successful pipeline run.

```json
{
  "last_checked": "2026-06-27T12:00:00Z",
  "last_status": "success | fetch_error | notify_error",
  "sources": {
    "coinbase": {
      "last_checked": "2026-06-27T12:00:00Z",
      "roles": {
        "5948877": {
          "title": "Software Engineering Intern",
          "location": "Remote - USA",
          "url": "https://boards.greenhouse.io/coinbase/jobs/5948877",
          "updated_at": "2026-06-20T10:30:00Z",
          "first_seen": "2026-06-21T08:00:00Z"
        }
      }
    }
  }
}
```

**Key design decisions:**

- Roles are keyed by their ATS-assigned `id` (the stable unique identifier). This is the primary key for diffing. Title changes on the same ID = same role, not a new one.
- `first_seen` records when the system first detected the role. This is set once and never updated. Useful for debugging and future features (e.g., "this role has been open for 3 weeks").
- Each source gets its own namespace under `sources`. This keeps state isolated per company/board and makes adding new sources trivial.
- `last_status` provides observability. If the system errors, the next run can see what happened.

### 3.3 Source Registry Schema

`sources.yaml` declares all monitored companies and their ATS configuration:

```yaml
sources:
  - name: coinbase
    display_name: Coinbase
    ats: greenhouse
    boards:
      - coinbase
      - cdpjobs
```

**Why two boards for Coinbase:** Coinbase operates two separate Greenhouse job boards — `coinbase` (the main company board) and `cdpjobs` (Coinbase Developer Platform). Both must be queried and their results merged and deduplicated by job `id` before entering the filter stage.

---

## 4. Pipeline Stages — Detailed

### 4.1 Fetch Stage

**Responsibility:** Retrieve raw job data from the ATS API for each configured source.

**Greenhouse Job Board API:**

- **Endpoint:** `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`
- **Authentication:** None required for GET endpoints. The Job Board API is fully public.
- **Response format:** JSON. Returns a top-level object with a `jobs` array.
- **Pagination:** Not needed. The endpoint returns all jobs in a single response.
- **Rate limiting:** Not a concern at one request per board per day.

**Response shape from Greenhouse:**

```json
{
  "jobs": [
    {
      "id": 5948877,
      "title": "Staff Software Engineer, Backend",
      "updated_at": "2026-06-20T10:30:00-05:00",
      "location": {
        "name": "Remote - USA"
      },
      "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/5948877",
      "internal_job_id": 5948800,
      "requisition_id": "GPBE06US",
      "metadata": [],
      "departments": [],
      "offices": []
    }
  ]
}
```

**Fields used:**

| Field | Purpose |
|---|---|
| `id` | Primary key for diff/deduplication. Stable across title edits. |
| `title` | Displayed in email. Used for intern keyword filtering. |
| `location.name` | Displayed in email for geographic context. |
| `absolute_url` | Direct apply link included in email. |
| `updated_at` | Metadata for debugging. Not used in diff logic. |

**Fields ignored:** `internal_job_id`, `requisition_id`, `metadata`, `departments`, `offices`. These are available if future filtering needs them (e.g., filter by department) but are not needed for the initial implementation.

**For Coinbase specifically,** the fetch stage makes two HTTP requests:

```
GET https://boards-api.greenhouse.io/v1/boards/coinbase/jobs
GET https://boards-api.greenhouse.io/v1/boards/cdpjobs/jobs
```

Results are concatenated into a single list and deduplicated by `id` before proceeding.

**Error handling:**

- If the HTTP response status is not 200, or the response body does not contain a `jobs` array, the fetch is marked as failed for that source.
- A failed fetch does **not** produce an empty job list. It aborts the pipeline for that source entirely. This prevents the diff stage from interpreting a fetch failure as "all roles have been removed," which would cause every existing role to appear as "new" on the next successful run.
- The system should log the error and send a notification indicating the check failed (distinct from "no new roles").

### 4.2 Normalize Stage

**Responsibility:** Convert ATS-specific response shapes into the canonical `Job` schema.

For Greenhouse, the transformation is:

```python
def normalize_greenhouse_job(raw_job, source_name):
    return {
        "id": str(raw_job["id"]),
        "title": raw_job["title"],
        "location": raw_job.get("location", {}).get("name", "Unknown"),
        "url": raw_job["absolute_url"],
        "updated_at": raw_job["updated_at"],
        "source": source_name
    }
```

**Why this stage exists even with only one ATS:** The normalize stage is what makes adding company #2 trivial. If the next company uses Lever or Ashby, only a new normalize function is needed. The filter, diff, and notify stages never change because they only see the canonical shape.

### 4.3 Filter Stage

**Responsibility:** Apply user-defined criteria to determine which roles are relevant.

**Current criteria:** A role matches if its title contains the substring "intern" (case-insensitive).

```python
def matches_criteria(job):
    return "intern" in job["title"].lower()
```

**Known limitations and edge cases:**

- **False negatives:** Roles titled "Summer Associate" or "Rotational Program" that are functionally internships will be missed. Acceptable for v1; can be improved later with a more sophisticated matcher (regex patterns, keyword list).
- **False positives:** Roles like "Internal Tools Engineer" contain "intern" as a substring. At the scale of one company with ~10–50 roles, the occasional false positive in an email is acceptable and can be manually ignored.
- **The filter is its own stage** so that criteria changes (adding location preferences, team filters, exclusion keywords) don't require touching fetch or diff logic.

### 4.4 Diff Stage

**Responsibility:** Compare the current set of filtered roles against the previously stored state to identify new roles.

**Algorithm:** Set subtraction keyed on job `id`.

```python
current_ids = set(current_filtered_roles.keys())
previous_ids = set(previous_state_roles.keys())

new_ids = current_ids - previous_ids
```

Any role whose `id` appears in `current_ids` but not in `previous_ids` is a new role. That's the complete list that goes into the email.

**What about re-posted roles?** If Coinbase closes a role and re-posts it with a new Greenhouse ID, it will appear as a new role — which is correct behavior, because it is a genuinely new application opportunity. If they re-post with the same ID (which Greenhouse doesn't typically do), it would be treated as existing and ignored — also correct, because the posting hasn't materially changed.

### 4.5 Notify Stage

**Responsibility:** Compose and send the daily email digest via the Gmail API.

**Email states:**

**State 1 — New roles found:**

```
Subject: 🆕 {N} new intern role(s) at Coinbase — {date}

{N} new intern role(s) detected at Coinbase:

1. Software Engineering Intern
   📍 Remote - USA
   🔗 https://boards.greenhouse.io/coinbase/jobs/1234567

2. Data Science Intern
   📍 New York, NY
   🔗 https://boards.greenhouse.io/coinbase/jobs/7654321

---
Checked at {timestamp}. System status: healthy.
```

**State 2 — No new roles:**

```
Subject: ✅ No new intern roles at Coinbase — {date}

No new intern roles detected at Coinbase today.

---
Checked at {timestamp}. System status: healthy.
```

**State 3 — System error:**

```
Subject: ⚠️ Job monitor error — {date}

The job monitor encountered an error while checking Coinbase:
{error description}

The check will be retried on the next scheduled run.
Previous state has been preserved (no data lost).

---
Attempted at {timestamp}.
```

**Why the "no new roles" email is sent:** Silence is ambiguous. If no email arrives, the user can't tell whether nothing was found or the system broke. The daily "all clear" email serves as a heartbeat — proof the system ran successfully. Think of it like a security guard radioing "all clear" during rounds.

**Gmail API integration:** Covered in a later section of this spec (to be added).

### 4.6 State Update

**Responsibility:** Persist the current set of roles to the state file after a successful pipeline run.

**Critical sequencing:** The state file is updated **only after the notification email has been confirmed sent.** The execution order is:

```
1. Read state.json from repo
2. Fetch roles from Greenhouse API
3. Normalize into canonical schema
4. Filter for intern roles
5. Diff against stored state → compute new_roles
6. Compose and send email
7. ✅ Email send confirmed
8. NOW update state.json with current roles
9. Commit and push state.json to git
```

If any step fails before step 7, the state file remains unchanged. On the next run, the system retries with the same baseline and catches anything it missed. This is the same principle as a database transaction — don't commit until the full operation succeeds.

---

## 5. Cold Start Handling

The first time the pipeline runs, there is no `state.json` file. Every role would appear as "new," flooding the user with notifications for roles that may have been open for weeks.

**Bootstrap behavior:**

1. Detect that `state.json` does not exist.
2. Fetch and filter roles as normal.
3. Write `state.json` with the full current set of roles (all `first_seen` timestamps set to now).
4. Send a bootstrap email: *"System initialized. Currently tracking {N} intern roles at Coinbase."* — list the roles for reference but do not present them as "new."
5. No individual "new role" notifications on this run.

From the second run onward, the diff operates normally against the bootstrapped baseline.

---

## 6. Execution Environment

### 6.1 GitHub Actions

The pipeline runs as a scheduled GitHub Actions workflow.

**Why GitHub Actions over self-hosted cron:**
- Zero infrastructure to maintain. No server to keep running, no process to monitor.
- Built-in retry, logging, and failure notifications.
- The repo is already on GitHub (for the state file), so the workflow is co-located with the code.

**Schedule:** Daily at 12:00 UTC (approximately 8:00 AM ET, accounting for daylight saving time). Configured via cron syntax in the workflow file.

```yaml
on:
  schedule:
    - cron: '0 12 * * *'
```

**Important:** GitHub Actions cron is not guaranteed to run at the exact scheduled time. There can be delays of several minutes during high-demand periods. This is acceptable for a daily digest — the email arriving at 8:03 AM instead of 8:00 AM is fine.

### 6.2 Secrets and Configuration

The following secrets must be stored in the GitHub repository's Actions secrets:

| Secret | Purpose |
|---|---|
| `GMAIL_CREDENTIALS` | OAuth2 credentials JSON for the Gmail API |
| `GMAIL_TOKEN` | OAuth2 refresh token for the user's Gmail account |
| `NOTIFY_EMAIL` | The recipient email address for notifications |

### 6.3 Workflow Steps

```yaml
jobs:
  check-jobs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements.txt
      - run: python main.py
        env:
          GMAIL_CREDENTIALS: ${{ secrets.GMAIL_CREDENTIALS }}
          GMAIL_TOKEN: ${{ secrets.GMAIL_TOKEN }}
          NOTIFY_EMAIL: ${{ secrets.NOTIFY_EMAIL }}
      - uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: "chore: update job state [skip ci]"
          file_pattern: state.json
```

The `[skip ci]` in the commit message prevents the state file commit from triggering another workflow run.

---

## 7. Project Structure

```
job-monitor/
├── main.py                  # Entry point — orchestrates the pipeline
├── sources.yaml             # Source registry (companies, ATS config, board tokens)
├── state.json               # Persisted state (committed to git, created on first run)
├── requirements.txt         # Python dependencies
├── .github/
│   └── workflows/
│       └── check-jobs.yml   # GitHub Actions workflow
├── adapters/
│   ├── __init__.py
│   └── greenhouse.py        # Greenhouse ATS adapter (fetch + normalize)
├── pipeline/
│   ├── __init__.py
│   ├── filter.py            # Criteria matching logic
│   ├── diff.py              # Set subtraction diff engine
│   └── state.py             # State file read/write operations
├── notify/
│   ├── __init__.py
│   └── gmail.py             # Gmail API email composition and sending
└── README.md
```

---

## 8. Dependencies

### 8.1 Python Packages

| Package | Purpose |
|---|---|
| `requests` | HTTP client for Greenhouse API calls |
| `google-auth` | Google OAuth2 authentication |
| `google-auth-oauthlib` | OAuth2 flow helpers |
| `google-api-python-client` | Gmail API client |
| `pyyaml` | Parse `sources.yaml` |

### 8.2 External Services

| Service | Purpose | Auth Required |
|---|---|---|
| Greenhouse Job Board API | Fetch job postings | No (public GET endpoints) |
| Gmail API | Send notification emails | Yes (OAuth2) |
| GitHub Actions | Scheduled pipeline execution | Yes (repo access token, automatic) |

---

## 9. Error Handling Summary

| Failure Point | Behavior |
|---|---|
| Greenhouse API returns non-200 | Abort pipeline for that source. Send error notification email. State unchanged. |
| Greenhouse API returns 200 but malformed JSON | Same as above. |
| Greenhouse API returns 200 but empty `jobs` array | Proceed normally — this is a valid state (all jobs may have been taken down). Diff will detect removals but we don't act on those. |
| Gmail API fails to send | State is NOT updated. Roles detected as "new" will be detected again on the next run. Log the error. |
| `state.json` doesn't exist | Cold start bootstrap (see Section 5). |
| `state.json` is corrupted or unparseable | Treat as cold start. Re-bootstrap and send initialization email. Log warning. |
| Git commit/push fails after successful email | Email was sent (user is notified), but state wasn't persisted. Next run will re-detect the same new roles and send a duplicate notification. Acceptable — a duplicate is better than a miss. |

---

## 10. Future Considerations

These are documented for context but are explicitly **out of scope** for the initial implementation.

- **Multiple companies:** The architecture supports this via `sources.yaml`. Adding a company means adding an entry and potentially a new ATS adapter.
- **Multiple ATS adapters:** Lever, Ashby, Workday each have their own public APIs. Each gets an adapter module in `adapters/` that implements fetch + normalize.
- **Richer filtering:** Location preferences, team/department filters, exclusion keywords, regex patterns.
- **Frequency increase:** Twice-daily checks to catch roles that post and fill within hours.
- **Notification channels:** Discord webhooks (originally planned), Slack, SMS.
- **Role removal detection:** Flagging when a role disappears (application window closed).
- **Project B integration:** Discovery pipeline for finding new companies to monitor, feeding into the `sources.yaml` registry.

---

## 11. Remaining Work (To Be Specified)

The following sections will be added as we continue design discussions:

- [ ] **Gmail API integration details** — OAuth2 setup, credential management, email composition via the API, HTML vs. plain text email format.
- [ ] **Detailed implementation plan** — Step-by-step build order, which files to create first, testing strategy.
- [ ] **Local development workflow** — How to run the pipeline locally for testing without waiting for GitHub Actions.
