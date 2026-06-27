def compute_new_roles(current_jobs: list[dict], previous_roles: dict) -> list[dict]:
    """Return jobs whose id is not present in the previous state."""
    previous_ids = set(previous_roles.keys())
    return [job for job in current_jobs if job["id"] not in previous_ids]
