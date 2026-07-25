import requests

WORKDAY_PAGE_LIMIT = 20


def _board_label(board: dict) -> str:
    return f"{board['tenant']}/{board['site']}"


def _board_url(board: dict) -> str:
    return f"https://{board['tenant']}.{board['wd']}.myworkdayjobs.com/wday/cxs/{board['tenant']}/{board['site']}/jobs"


def _fetch_board(board: dict) -> list[dict]:
    url = _board_url(board)
    label = _board_label(board)

    all_postings: list[dict] = []
    offset = 0

    while True:
        response = requests.post(
            url,
            json={"appliedFacets": {}, "limit": WORKDAY_PAGE_LIMIT, "offset": offset, "searchText": ""},
            timeout=30,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"Workday API returned {response.status_code} for board '{label}': {response.text[:200]}"
            )

        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError(f"Workday API returned non-JSON for board '{label}': {e}")

        if "jobPostings" not in data:
            raise RuntimeError(
                f"Workday API response for board '{label}' missing 'jobPostings' key"
            )

        postings = data["jobPostings"]
        all_postings.extend(postings)

        total = data.get("total", 0)
        offset += WORKDAY_PAGE_LIMIT
        if not postings or offset >= total:
            break

    return all_postings


def _normalize(raw_job: dict, source_name: str, board: dict) -> dict:
    external_path = raw_job["externalPath"]
    return {
        "id": external_path,
        "title": raw_job["title"],
        "location": raw_job.get("locationsText") or "Unknown",
        "url": f"https://{board['tenant']}.{board['wd']}.myworkdayjobs.com/en-US/{board['site']}{external_path}",
        "updated_at": raw_job.get("postedOn") or "Unknown",
        "source": source_name,
    }


def fetch_all_for_source(source: dict) -> list[dict]:
    """Fetch and normalize jobs from all Workday boards for a source, deduplicated by id."""
    source_name = source["name"]
    boards = source["boards"]

    seen_ids: set[str] = set()
    jobs: list[dict] = []

    for board in boards:
        raw_postings = _fetch_board(board)
        for raw in raw_postings:
            job = _normalize(raw, source_name, board)
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                jobs.append(job)

    return jobs
