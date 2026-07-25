import sys
import yaml
from datetime import datetime, timezone

from adapters.greenhouse import fetch_all_for_source as fetch_greenhouse
from adapters.ashby import fetch_all_for_source as fetch_ashby
from pipeline.filter import filter_jobs
from pipeline.diff import compute_new_roles
from pipeline.state import load_state, save_state, build_roles_snapshot
from notify.gmail import send_email

ATS_ADAPTERS = {
    "greenhouse": fetch_greenhouse,
    "ashby": fetch_ashby,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_role(job: dict, index: int) -> str:
    return f"{index}. {job['title']}\n   📍 {job['location']}\n   🔗 {job['url']}"


def _send_combined_bootstrap_email(sources_data: list[dict], timestamp: str) -> None:
    """Send one bootstrap email summarizing all newly initialized sources."""
    total_roles = sum(len(d["jobs"]) for d in sources_data)
    sections = []
    for d in sources_data:
        name = d["display_name"]
        roles = d["jobs"]
        count = len(roles)
        if count == 0:
            sections.append(f"--- {name} ---\nNo open roles found.")
        else:
            role_lines = "\n\n".join(_format_role(r, i + 1) for i, r in enumerate(roles))
            sections.append(f"--- {name} ({count} role(s)) ---\n\n{role_lines}")
    body = (
        f"System initialized for {len(sources_data)} source(s). "
        f"Currently tracking {total_roles} total role(s):\n\n"
        + "\n\n".join(sections)
        + f"\n\n---\nInitialized at {timestamp}. Future runs will notify you of new roles only."
    )
    send_email(f"🚀 Job monitor initialized — {len(sources_data)} source(s)", body)


def _send_combined_update_email(updates: list[dict], timestamp: str) -> None:
    """Send one email summarizing all sources checked this run."""
    date_str = timestamp[:10]
    total_new = sum(len(u["new_roles"]) for u in updates)
    companies_with_new = sum(1 for u in updates if u["new_roles"])

    sections = []
    for u in updates:
        name = u["display_name"]
        new_roles = u["new_roles"]
        if new_roles:
            count = len(new_roles)
            role_lines = "\n\n".join(_format_role(r, i + 1) for i, r in enumerate(new_roles))
            sections.append(f"--- {name} ({count} new role(s)) ---\n\n{role_lines}")
        else:
            sections.append(f"--- {name} ---\nNo new roles.")

    if total_new:
        subject = f"🆕 {total_new} new intern role(s) at {companies_with_new} company/companies — {date_str}"
    else:
        subject = f"✅ No new intern roles today — {date_str}"

    body = (
        "\n\n".join(sections)
        + f"\n\n---\nChecked at {timestamp}. System status: healthy."
    )
    send_email(subject, body)


def _send_error_email(display_name: str, error: str, timestamp: str) -> None:
    date_str = timestamp[:10]
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
    bootstrap_queue: list[dict] = []  # accumulates data for the single combined bootstrap email
    notify_queue: list[dict] = []     # accumulates per-source diffs for the single combined update email

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

        existing_roles = (
            state.get("sources", {}).get(source_name, {}).get("roles", {})
        )

        if is_cold_start:
            # Collect — combined email sent after the loop
            bootstrap_queue.append({
                "source_name": source_name,
                "display_name": display_name,
                "jobs": intern_jobs,
            })
        else:
            # --- Diff ---
            new_roles = compute_new_roles(intern_jobs, existing_roles)
            print(f"[{source_name}] {len(new_roles)} new role(s) detected.")

            # Collect — combined email sent after the loop
            notify_queue.append({
                "source_name": source_name,
                "display_name": display_name,
                "new_roles": new_roles,
                "intern_jobs": intern_jobs,
                "existing_roles": existing_roles,
            })

    # --- Combined update email (one email for all sources) ---
    if notify_queue:
        try:
            _send_combined_update_email(notify_queue, timestamp)
        except Exception as e:
            print(f"[main] Failed to send combined update email: {e}")
            overall_status = "notify_error"
            # Critical: do NOT update state — all sources will re-detect next run
        else:
            for item in notify_queue:
                snapshot = build_roles_snapshot(item["intern_jobs"], item["existing_roles"], timestamp)
                if "sources" not in state:
                    state["sources"] = {}
                state["sources"][item["source_name"]] = {
                    "last_checked": timestamp,
                    "roles": snapshot,
                }

    # --- Combined bootstrap email (one email for all new sources) ---
    if bootstrap_queue:
        try:
            _send_combined_bootstrap_email(bootstrap_queue, timestamp)
        except Exception as e:
            print(f"[main] Failed to send combined bootstrap email: {e}")
            overall_status = "notify_error"
            # Don't save any bootstrap state — all sources will retry next run
        else:
            for item in bootstrap_queue:
                snapshot = build_roles_snapshot(item["jobs"], {}, timestamp)
                if "sources" not in state:
                    state["sources"] = {}
                state["sources"][item["source_name"]] = {
                    "last_checked": timestamp,
                    "roles": snapshot,
                }

    state["last_status"] = overall_status
    save_state(state)
    print(f"[main] Done. Status: {overall_status}")
    return 0 if overall_status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
