import json
import os
from datetime import datetime, timezone

STATE_FILE = "state.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state() -> tuple[dict, bool]:
    """
    Returns (state, is_cold_start).
    is_cold_start is True when the state file is missing or unreadable.
    """
    if not os.path.exists(STATE_FILE):
        return _empty_state(), True

    try:
        with open(STATE_FILE) as f:
            state = json.load(f)
        if not isinstance(state, dict) or "sources" not in state:
            raise ValueError("Unexpected state shape")
        return state, False
    except Exception as e:
        print(f"[state] Warning: could not parse {STATE_FILE} ({e}). Treating as cold start.")
        return _empty_state(), True


def save_state(state: dict) -> None:
    state["last_checked"] = _now_iso()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def _empty_state() -> dict:
    return {
        "last_checked": None,
        "last_status": None,
        "sources": {},
    }


def build_roles_snapshot(jobs: list[dict], existing_roles: dict, first_seen_ts: str) -> dict:
    """
    Build the roles dict for state.json from a list of canonical jobs.
    Preserves existing first_seen timestamps; uses first_seen_ts for new entries.
    """
    snapshot = {}
    for job in jobs:
        jid = job["id"]
        snapshot[jid] = {
            "title": job["title"],
            "location": job["location"],
            "url": job["url"],
            "updated_at": job["updated_at"],
            "first_seen": existing_roles.get(jid, {}).get("first_seen", first_seen_ts),
        }
    return snapshot
