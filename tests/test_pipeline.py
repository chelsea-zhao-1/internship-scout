"""
Full scenario test suite — no network calls, no Gmail calls.
Covers every pipeline state described in the spec.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_SINGLE_SOURCE_YAML = (
    "sources:\n"
    "  - name: coinbase\n"
    "    display_name: Coinbase\n"
    "    ats: greenhouse\n"
    "    boards:\n"
    "      - coinbase\n"
)

INTERN_JOB_RAW = {
    "id": 1001,
    "title": "Software Engineering Intern",
    "location": {"name": "Remote - USA"},
    "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/1001",
    "updated_at": "2026-06-01T00:00:00Z",
}

NON_INTERN_JOB_RAW = {
    "id": 2001,
    "title": "Staff Software Engineer",
    "location": {"name": "New York, NY"},
    "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/2001",
    "updated_at": "2026-06-01T00:00:00Z",
}

INTERNAL_FALSE_POSITIVE_RAW = {
    "id": 3001,
    "title": "Internal Audit Analyst",
    "location": {"name": "Remote - USA"},
    "absolute_url": "https://boards.greenhouse.io/coinbase/jobs/3001",
    "updated_at": "2026-06-01T00:00:00Z",
}

SOURCE = {
    "name": "coinbase",
    "display_name": "Coinbase",
    "ats": "greenhouse",
    "boards": ["coinbase"],
}


def _make_greenhouse_response(jobs):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"jobs": jobs}
    return mock


def _make_state(roles_by_id: dict) -> dict:
    return {
        "last_checked": "2026-06-26T12:00:00Z",
        "last_status": "success",
        "sources": {
            "coinbase": {
                "last_checked": "2026-06-26T12:00:00Z",
                "roles": roles_by_id,
            }
        },
    }


# ---------------------------------------------------------------------------
# Unit: greenhouse adapter
# ---------------------------------------------------------------------------

class TestGreenhouseAdapter:
    def test_normalize_maps_fields(self):
        from adapters.greenhouse import _normalize
        job = _normalize(INTERN_JOB_RAW, "coinbase")
        assert job["id"] == "1001"
        assert job["title"] == "Software Engineering Intern"
        assert job["location"] == "Remote - USA"
        assert job["url"] == "https://boards.greenhouse.io/coinbase/jobs/1001"
        assert job["source"] == "coinbase"

    def test_normalize_missing_location(self):
        from adapters.greenhouse import _normalize
        raw = {**INTERN_JOB_RAW, "location": None}
        job = _normalize(raw, "coinbase")
        assert job["location"] == "Unknown"

    @patch("adapters.greenhouse.requests.get")
    def test_fetch_board_success(self, mock_get):
        from adapters.greenhouse import _fetch_board
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])
        jobs = _fetch_board("coinbase")
        assert len(jobs) == 1
        assert jobs[0]["id"] == 1001

    @patch("adapters.greenhouse.requests.get")
    def test_fetch_board_non_200_raises(self, mock_get):
        from adapters.greenhouse import _fetch_board
        mock_get.return_value = MagicMock(status_code=500, text="error")
        with pytest.raises(RuntimeError, match="500"):
            _fetch_board("coinbase")

    @patch("adapters.greenhouse.requests.get")
    def test_fetch_board_missing_jobs_key_raises(self, mock_get):
        from adapters.greenhouse import _fetch_board
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = {"not_jobs": []}
        with pytest.raises(RuntimeError, match="missing 'jobs'"):
            _fetch_board("coinbase")

    @patch("adapters.greenhouse.requests.get")
    def test_deduplication_across_boards(self, mock_get):
        from adapters.greenhouse import fetch_all_for_source
        # Same job id returned from two boards
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])
        source = {**SOURCE, "boards": ["coinbase", "cdpjobs"]}
        jobs = fetch_all_for_source(source)
        assert len(jobs) == 1  # deduplicated

    @patch("adapters.greenhouse.requests.get")
    def test_empty_jobs_array_is_valid(self, mock_get):
        from adapters.greenhouse import fetch_all_for_source
        mock_get.return_value = _make_greenhouse_response([])
        jobs = fetch_all_for_source(SOURCE)
        assert jobs == []


# ---------------------------------------------------------------------------
# Unit: ashby adapter
# ---------------------------------------------------------------------------

ASHBY_INTERN_JOB_RAW = {
    "id": "05e14247-17c4-4e98-9a13-53828a4e2f13",
    "title": "Software Engineering Intern",
    "location": "New York, New York",
    "publishedAt": "2026-04-02T21:00:55.755+00:00",
    "jobUrl": "https://jobs.ashbyhq.com/acme/05e14247-17c4-4e98-9a13-53828a4e2f13",
    "applyUrl": "https://jobs.ashbyhq.com/acme/05e14247-17c4-4e98-9a13-53828a4e2f13/application",
}

ASHBY_SOURCE = {
    "name": "acme",
    "display_name": "Acme",
    "ats": "ashby",
    "boards": ["acme"],
}


def _make_ashby_response(jobs):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"jobs": jobs, "apiVersion": "1"}
    return mock


class TestAshbyAdapter:
    def test_normalize_maps_fields(self):
        from adapters.ashby import _normalize
        job = _normalize(ASHBY_INTERN_JOB_RAW, "acme")
        assert job["id"] == "05e14247-17c4-4e98-9a13-53828a4e2f13"
        assert job["title"] == "Software Engineering Intern"
        assert job["location"] == "New York, New York"
        assert job["url"] == "https://jobs.ashbyhq.com/acme/05e14247-17c4-4e98-9a13-53828a4e2f13"
        assert job["source"] == "acme"

    def test_normalize_missing_location(self):
        from adapters.ashby import _normalize
        raw = {**ASHBY_INTERN_JOB_RAW, "location": None}
        job = _normalize(raw, "acme")
        assert job["location"] == "Unknown"

    @patch("adapters.ashby.requests.get")
    def test_fetch_board_success(self, mock_get):
        from adapters.ashby import _fetch_board
        mock_get.return_value = _make_ashby_response([ASHBY_INTERN_JOB_RAW])
        jobs = _fetch_board("acme")
        assert len(jobs) == 1
        assert jobs[0]["id"] == "05e14247-17c4-4e98-9a13-53828a4e2f13"

    @patch("adapters.ashby.requests.get")
    def test_fetch_board_non_200_raises(self, mock_get):
        from adapters.ashby import _fetch_board
        mock_get.return_value = MagicMock(status_code=404, text="Not Found")
        with pytest.raises(RuntimeError, match="404"):
            _fetch_board("acme")

    @patch("adapters.ashby.requests.get")
    def test_fetch_board_missing_jobs_key_raises(self, mock_get):
        from adapters.ashby import _fetch_board
        mock_get.return_value = MagicMock(status_code=200)
        mock_get.return_value.json.return_value = {"not_jobs": []}
        with pytest.raises(RuntimeError, match="missing 'jobs'"):
            _fetch_board("acme")

    @patch("adapters.ashby.requests.get")
    def test_deduplication_across_boards(self, mock_get):
        from adapters.ashby import fetch_all_for_source
        mock_get.return_value = _make_ashby_response([ASHBY_INTERN_JOB_RAW])
        source = {**ASHBY_SOURCE, "boards": ["acme", "acme-alt"]}
        jobs = fetch_all_for_source(source)
        assert len(jobs) == 1  # deduplicated

    @patch("adapters.ashby.requests.get")
    def test_empty_jobs_array_is_valid(self, mock_get):
        from adapters.ashby import fetch_all_for_source
        mock_get.return_value = _make_ashby_response([])
        jobs = fetch_all_for_source(ASHBY_SOURCE)
        assert jobs == []


# ---------------------------------------------------------------------------
# Unit: filter
# ---------------------------------------------------------------------------

class TestFilter:
    def test_intern_title_matches(self):
        from pipeline.filter import matches_criteria
        assert matches_criteria({"title": "Software Engineering Intern"})

    def test_case_insensitive(self):
        from pipeline.filter import matches_criteria
        assert matches_criteria({"title": "INTERN Program"})

    def test_non_intern_title_no_match(self):
        from pipeline.filter import matches_criteria
        assert not matches_criteria({"title": "Staff Software Engineer"})

    def test_internal_not_matched(self):
        from pipeline.filter import matches_criteria
        # "internal" must NOT match — whole-word check, not substring
        assert not matches_criteria({"title": "Internal Audit Analyst"})

    def test_international_not_matched(self):
        from pipeline.filter import matches_criteria
        assert not matches_criteria({"title": "International Operations Manager"})

    def test_internship_matches(self):
        from pipeline.filter import matches_criteria
        assert matches_criteria({"title": "Summer Internship - Trading"})

    def test_coop_matches(self):
        from pipeline.filter import matches_criteria
        assert matches_criteria({"title": "Software Engineering Co-op"})
        assert matches_criteria({"title": "Engineering Coop Program"})

    def test_filter_jobs_removes_non_interns(self):
        from pipeline.filter import filter_jobs
        from adapters.greenhouse import _normalize
        jobs = [
            _normalize(INTERN_JOB_RAW, "coinbase"),
            _normalize(NON_INTERN_JOB_RAW, "coinbase"),
        ]
        result = filter_jobs(jobs)
        assert len(result) == 1
        assert result[0]["title"] == "Software Engineering Intern"


# ---------------------------------------------------------------------------
# Unit: diff
# ---------------------------------------------------------------------------

class TestDiff:
    def test_all_new_when_previous_empty(self):
        from pipeline.diff import compute_new_roles
        from adapters.greenhouse import _normalize
        jobs = [_normalize(INTERN_JOB_RAW, "coinbase")]
        new = compute_new_roles(jobs, {})
        assert len(new) == 1

    def test_no_new_when_already_seen(self):
        from pipeline.diff import compute_new_roles
        from adapters.greenhouse import _normalize
        jobs = [_normalize(INTERN_JOB_RAW, "coinbase")]
        previous = {"1001": {"title": "Software Engineering Intern"}}
        new = compute_new_roles(jobs, previous)
        assert new == []

    def test_detects_genuinely_new_role(self):
        from pipeline.diff import compute_new_roles
        from adapters.greenhouse import _normalize
        existing_job = _normalize(INTERN_JOB_RAW, "coinbase")
        new_raw = {**INTERN_JOB_RAW, "id": 9999, "title": "Data Science Intern"}
        new_job = _normalize(new_raw, "coinbase")
        previous = {"1001": {}}
        new = compute_new_roles([existing_job, new_job], previous)
        assert len(new) == 1
        assert new[0]["id"] == "9999"

    def test_role_removal_not_flagged(self):
        from pipeline.diff import compute_new_roles
        # A role in previous but not current is just ignored (not flagged)
        previous = {"1001": {}, "5555": {}}
        new = compute_new_roles([], previous)
        assert new == []


# ---------------------------------------------------------------------------
# Unit: state
# ---------------------------------------------------------------------------

class TestState:
    def test_cold_start_when_no_file(self, tmp_path, monkeypatch):
        from pipeline import state as state_mod
        monkeypatch.chdir(tmp_path)
        s, cold = state_mod.load_state()
        assert cold is True
        assert s["sources"] == {}

    def test_cold_start_on_corrupted_file(self, tmp_path, monkeypatch):
        from pipeline import state as state_mod
        monkeypatch.chdir(tmp_path)
        (tmp_path / "state.json").write_text("not valid json!!!")
        s, cold = state_mod.load_state()
        assert cold is True

    def test_cold_start_on_wrong_shape(self, tmp_path, monkeypatch):
        from pipeline import state as state_mod
        monkeypatch.chdir(tmp_path)
        (tmp_path / "state.json").write_text(json.dumps(["unexpected", "list"]))
        s, cold = state_mod.load_state()
        assert cold is True

    def test_normal_load(self, tmp_path, monkeypatch):
        from pipeline import state as state_mod
        monkeypatch.chdir(tmp_path)
        (tmp_path / "state.json").write_text(json.dumps(_make_state({"1001": {}})))
        s, cold = state_mod.load_state()
        assert cold is False
        assert "1001" in s["sources"]["coinbase"]["roles"]

    def test_save_writes_file(self, tmp_path, monkeypatch):
        from pipeline import state as state_mod
        monkeypatch.chdir(tmp_path)
        state_mod.save_state({"sources": {}, "last_status": "success"})
        data = json.loads((tmp_path / "state.json").read_text())
        assert "last_checked" in data

    def test_build_roles_snapshot_preserves_first_seen(self):
        from pipeline.state import build_roles_snapshot
        from adapters.greenhouse import _normalize
        job = _normalize(INTERN_JOB_RAW, "coinbase")
        existing = {"1001": {"first_seen": "2026-06-01T00:00:00Z"}}
        snap = build_roles_snapshot([job], existing, "2026-06-27T00:00:00Z")
        assert snap["1001"]["first_seen"] == "2026-06-01T00:00:00Z"

    def test_build_roles_snapshot_sets_first_seen_for_new(self):
        from pipeline.state import build_roles_snapshot
        from adapters.greenhouse import _normalize
        job = _normalize(INTERN_JOB_RAW, "coinbase")
        snap = build_roles_snapshot([job], {}, "2026-06-27T00:00:00Z")
        assert snap["1001"]["first_seen"] == "2026-06-27T00:00:00Z"


# ---------------------------------------------------------------------------
# Scenario: cold start (bootstrap)
# ---------------------------------------------------------------------------

class TestScenarioColdStart:
    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_bootstrap_email_sent_no_new_roles_email(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        exit_code = main()

        assert exit_code == 0
        assert mock_send.call_count == 1
        subject, body = mock_send.call_args[0]
        assert "initialized" in subject.lower()
        assert "Software Engineering Intern" in body

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_state_saved_after_bootstrap(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        main()

        state = json.loads((tmp_path / "state.json").read_text())
        assert "1001" in state["sources"]["coinbase"]["roles"]

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_bootstrap_with_no_intern_roles(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        mock_get.return_value = _make_greenhouse_response([NON_INTERN_JOB_RAW])

        from main import main
        main()

        subject, body = mock_send.call_args[0]
        assert "initialized" in subject.lower()
        assert "No open roles found" in body


# ---------------------------------------------------------------------------
# Scenario: new roles detected
# ---------------------------------------------------------------------------

class TestScenarioNewRoles:
    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_new_role_email_sent(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        # State has no previous intern roles
        (tmp_path / "state.json").write_text(json.dumps(_make_state({})))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        exit_code = main()

        assert exit_code == 0
        subject, body = mock_send.call_args[0]
        assert "🆕" in subject
        assert "1 new intern" in subject.lower()
        assert "Software Engineering Intern" in body
        assert "Remote - USA" in body

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_state_updated_after_new_role(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        (tmp_path / "state.json").write_text(json.dumps(_make_state({})))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        main()

        state = json.loads((tmp_path / "state.json").read_text())
        assert "1001" in state["sources"]["coinbase"]["roles"]


# ---------------------------------------------------------------------------
# Scenario: no new roles (heartbeat)
# ---------------------------------------------------------------------------

class TestScenarioNoNewRoles:
    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_no_new_roles_email_sent(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        existing = {"1001": {"title": "Software Engineering Intern", "location": "Remote - USA",
                              "url": "x", "updated_at": "x", "first_seen": "x"}}
        (tmp_path / "state.json").write_text(json.dumps(_make_state(existing)))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        exit_code = main()

        assert exit_code == 0
        subject, body = mock_send.call_args[0]
        assert "✅" in subject
        assert "No new roles" in body

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_first_seen_preserved_on_no_new_roles(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        existing = {"1001": {"title": "x", "location": "x", "url": "x",
                              "updated_at": "x", "first_seen": "2026-06-01T00:00:00Z"}}
        (tmp_path / "state.json").write_text(json.dumps(_make_state(existing)))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        main()

        state = json.loads((tmp_path / "state.json").read_text())
        assert state["sources"]["coinbase"]["roles"]["1001"]["first_seen"] == "2026-06-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Scenario: fetch error
# ---------------------------------------------------------------------------

class TestScenarioFetchError:
    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_error_email_sent_on_fetch_failure(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        existing = {"1001": {"title": "x", "location": "x", "url": "x",
                              "updated_at": "x", "first_seen": "x"}}
        (tmp_path / "state.json").write_text(json.dumps(_make_state(existing)))
        mock_get.return_value = MagicMock(status_code=503, text="Service Unavailable")

        from main import main
        exit_code = main()

        assert exit_code == 1
        subject, body = mock_send.call_args[0]
        assert "⚠️" in subject
        assert "error" in subject.lower()

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_state_not_updated_on_fetch_error(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        original_state = _make_state({"1001": {"title": "x", "location": "x",
                                                "url": "x", "updated_at": "x", "first_seen": "x"}})
        (tmp_path / "state.json").write_text(json.dumps(original_state))
        mock_get.return_value = MagicMock(status_code=503, text="error")

        from main import main
        main()

        # last_status updated but source roles untouched
        state = json.loads((tmp_path / "state.json").read_text())
        assert "1001" in state["sources"]["coinbase"]["roles"]


# ---------------------------------------------------------------------------
# Scenario: notify error (Gmail fails)
# ---------------------------------------------------------------------------

class TestScenarioNotifyError:
    @patch("main.send_email", side_effect=Exception("Gmail API down"))
    @patch("adapters.greenhouse.requests.get")
    def test_state_not_updated_when_email_fails(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        # State is empty — new role would be detected, but email fails
        (tmp_path / "state.json").write_text(json.dumps(_make_state({})))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        exit_code = main()

        assert exit_code == 1
        state = json.loads((tmp_path / "state.json").read_text())
        # Role must NOT be saved — it should be re-detected on next run
        assert "1001" not in state["sources"]["coinbase"]["roles"]

    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_new_role_redetected_on_retry_after_notify_failure(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        (tmp_path / "state.json").write_text(json.dumps(_make_state({})))
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main

        # First run — email fails, state not updated
        mock_send.side_effect = Exception("Gmail API down")
        main()

        # Second run — email works, role re-detected from unchanged state
        mock_send.side_effect = None
        exit_code = main()

        assert exit_code == 0
        subject, _ = mock_send.call_args[0]
        assert "🆕" in subject


# ---------------------------------------------------------------------------
# Scenario: corrupted state treated as cold start
# ---------------------------------------------------------------------------

class TestScenarioCorruptedState:
    @patch("main.send_email")
    @patch("adapters.greenhouse.requests.get")
    def test_corrupted_state_triggers_bootstrap(self, mock_get, mock_send, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "sources.yaml").write_text(_SINGLE_SOURCE_YAML)
        monkeypatch.setenv("NOTIFY_EMAIL", "test@example.com")
        (tmp_path / "state.json").write_text("{bad json{{")
        mock_get.return_value = _make_greenhouse_response([INTERN_JOB_RAW])

        from main import main
        main()

        subject, _ = mock_send.call_args[0]
        assert "initialized" in subject.lower()
