def matches_criteria(job: dict) -> bool:
    return True  # filter disabled for testing — re-enable intern keyword check before prod


def filter_jobs(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if matches_criteria(j)]
