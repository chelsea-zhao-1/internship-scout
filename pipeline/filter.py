import re

# Whole-word intern-related keywords. Word boundaries (\b) keep this from
# matching substrings like "international" or "internal", which the old
# `"intern" in title` check let through. `co-?op` covers both "co-op" and
# "coop"; the trailing \b keeps it off "cooperative".
_KEYWORD_RE = re.compile(
    r"\b(intern|interns|internship|internships|co-?op)\b",
    re.IGNORECASE,
)


def matches_criteria(job: dict) -> bool:
    return bool(_KEYWORD_RE.search(job["title"]))


def filter_jobs(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if matches_criteria(j)]
