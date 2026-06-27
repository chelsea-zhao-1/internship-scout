import requests

GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"


def _fetch_board(board_token: str) -> list[dict]:
    url = f"{GREENHOUSE_API_BASE}/{board_token}/jobs"
    response = requests.get(url, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"Greenhouse API returned {response.status_code} for board '{board_token}': {response.text[:200]}"
        )

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"Greenhouse API returned non-JSON for board '{board_token}': {e}")

    if "jobs" not in data:
        raise RuntimeError(
            f"Greenhouse API response for board '{board_token}' missing 'jobs' key"
        )

    return data["jobs"]


def _normalize(raw_job: dict, source_name: str) -> dict:
    return {
        "id": str(raw_job["id"]),
        "title": raw_job["title"],
        "location": raw_job.get("location", {}).get("name", "Unknown"),
        "url": raw_job["absolute_url"],
        "updated_at": raw_job["updated_at"],
        "source": source_name,
    }


def fetch_all_for_source(source: dict) -> list[dict]:
    """Fetch and normalize jobs from all boards for a source, deduplicated by id."""
    source_name = source["name"]
    boards = source["boards"]

    seen_ids: set[str] = set()
    jobs: list[dict] = []

    for board_token in boards:
        raw_jobs = _fetch_board(board_token)
        for raw in raw_jobs:
            job = _normalize(raw, source_name)
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                jobs.append(job)

    return jobs
