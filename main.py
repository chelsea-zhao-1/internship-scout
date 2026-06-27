import sys
import yaml
from datetime import datetime, timezone

from adapters.greenhouse import fetch_all_for_source
from pipeline.filter import filter_jobs
from pipeline.diff import compute_new_roles
from pipeline.state import load_state, save_state, build_roles_snapshot
from notify.gmail import send_email

ATS_ADAPTERS = {
    "greenhouse": fetch_all_for_source,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_role(job: dict, index: int) -> str:
    return f"{index}. {job['title']}\n   📍 {job['location']}\n   🔗 {job['url']}"


def _send_bootstrap_email(display_name: str, roles: list[dict], timestamp: str) -> None:
    count = len(roles)
    role_lines = "\n\n".join(_format_role(r, i + 1) for i, r in enumerate(roles))
    body = (
        f"System initialized. Currently tracking {count} intern role(s) at {display_name}:\n\n"
        f"{role_lines}\n\n"
        f"---\n"
        f"Initialized at {timestamp}. Future runs will notify you of new roles only."
    )
    if count == 0:
        body = (
            f"System initialized. No intern roles currently found at {display_name}.\n\n"
            f"---\n"
            f"Initialized at {timestamp}. Future runs will notify you of new roles."
        )
    send_email(f"🚀 Job monitor initialized — {display_name}", body)


def _send_new_roles_email(display_name: str, new_roles: list[dict], timestamp: str) -> None:
    count = len(new_roles)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    role_lines = "\n\n".join(_format_role(r, i + 1) for i, r in enumerate(new_roles))
    body = (
        f"{count} new intern role(s) detected at {display_name}:\n\n"
        f"{role_lines}\n\n"
        f"---\n"
        f"Checked at {timestamp}. System status: healthy."
    )
    send_email(f"🆕 {count} new intern role(s) at {display_name} — {date_str}", body)


def _send_no_new_roles_email(display_name: str, timestamp: str) -> None:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = (
        f"No new intern roles detected at {display_name} today.\n\n"
        f"---\n"
        f"Checked at {timestamp}. System status: healthy."
    )
    send_email(f"✅ No new intern roles at {display_name} — {date_str}", body)


def _send_error_email(display_name: str, error: str, timestamp: str) -> None:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = (
        f"The job monitor encountered an error while checking {display_name}:\n"
        f"{error}\n\n"
        f"The check will be retried on the next scheduled run.\n"
        f"Previous state has been preserved (no data lost).\n\n"
        f"---\n"
        f"Attempted at {timestamp}."
    )
    send_email(f"⚠️ Job monitor error — {date_str}", body)


def main() -> int:
    with open("sources.yaml") as f:
        config = yaml.safe_load(f)

    state, is_cold_start = load_state()
    timestamp = _now_iso()

    if is_cold_start:
        print("[main] Cold start detected — bootstrapping state.")

    overall_status = "success"

    for source in config["sources"]:
        source_name = source["name"]
        display_name = source["display_name"]
        ats = source["ats"]

        fetch_fn = ATS_ADAPTERS.get(ats)
        if fetch_fn is None:
            print(f"[main] Unknown ATS '{ats}' for source '{source_name}'. Skipping.")
            continue

        # --- Fetch ---
        print(f"[{source_name}] Fetching from {ats}…")
        try:
            all_jobs = fetch_fn(source)
        except Exception as e:
            error_msg = str(e)
            print(f"[{source_name}] Fetch error: {error_msg}")
            overall_status = "fetch_error"
            try:
                _send_error_email(display_name, error_msg, timestamp)
            except Exception as notify_err:
                print(f"[{source_name}] Also failed to send error email: {notify_err}")
            continue

        print(f"[{source_name}] Fetched {len(all_jobs)} total job(s).")

        # --- Filter ---
        intern_jobs = filter_jobs(all_jobs)
        print(f"[{source_name}] {len(intern_jobs)} intern role(s) after filtering.")

        # Index by id for state storage
        intern_by_id = {j["id"]: j for j in intern_jobs}

        existing_roles = (
            state.get("sources", {}).get(source_name, {}).get("roles", {})
        )

        if is_cold_start:
            # --- Bootstrap ---
            try:
                _send_bootstrap_email(display_name, intern_jobs, timestamp)
            except Exception as e:
                print(f"[{source_name}] Failed to send bootstrap email: {e}")
                overall_status = "notify_error"
                # Don't save state — will retry on next run
                continue

            snapshot = build_roles_snapshot(intern_jobs, {}, timestamp)
        else:
            # --- Diff ---
            new_roles = compute_new_roles(intern_jobs, existing_roles)
            print(f"[{source_name}] {len(new_roles)} new role(s) detected.")

            # --- Notify (email must succeed before state update) ---
            try:
                if new_roles:
                    _send_new_roles_email(display_name, new_roles, timestamp)
                else:
                    _send_no_new_roles_email(display_name, timestamp)
            except Exception as e:
                print(f"[{source_name}] Failed to send email: {e}")
                overall_status = "notify_error"
                # Critical: do NOT update state — roles will be re-detected next run
                continue

            snapshot = build_roles_snapshot(intern_jobs, existing_roles, timestamp)

        # --- Update state (only after confirmed email send) ---
        if "sources" not in state:
            state["sources"] = {}
        state["sources"][source_name] = {
            "last_checked": timestamp,
            "roles": snapshot,
        }

    state["last_status"] = overall_status
    save_state(state)
    print(f"[main] Done. Status: {overall_status}")
    return 0 if overall_status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
