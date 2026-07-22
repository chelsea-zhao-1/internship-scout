import re

# Word-boundary match, so "Internal Audit" and "International Tax" no longer
# slip through. Also catches co-op postings, which several companies use as the
# label for what is functionally an internship.
_INTERN_PATTERN = re.compile(
    r"\b(intern|interns|internship|internships|co-?op|co-?ops)\b",
    re.IGNORECASE,
)

# Full-time roles that run the intern programs rather than being one. Requires
# BOTH a management head word and the intern word modifying "program" — a bare
# seniority word is not enough, or real postings like "Sales Project Manager
# Intern" would be dropped.
_MANAGEMENT_PATTERN = re.compile(
    r"\b(manager|director|head|lead|coordinator|recruiter)\b",
    re.IGNORECASE,
)
_INTERN_PROGRAM_PATTERN = re.compile(
    r"\b(intern|interns|internship|internships|co-?op|co-?ops)\b[\s,\-]*programm?e?s?\b",
    re.IGNORECASE,
)


def matches_criteria(job: dict) -> bool:
    title = job["title"]
    if _MANAGEMENT_PATTERN.search(title) and _INTERN_PROGRAM_PATTERN.search(title):
        return False
    return bool(_INTERN_PATTERN.search(title))


def filter_jobs(jobs: list[dict]) -> list[dict]:
    return [j for j in jobs if matches_criteria(j)]
