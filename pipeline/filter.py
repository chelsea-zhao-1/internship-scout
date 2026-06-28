def matches_criteria(job: dict) -> bool:
    return "intern" in job["title"].lower()


def filter_jobs(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if matches_criteria(j)]
