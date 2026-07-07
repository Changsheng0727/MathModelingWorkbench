from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app.main as main


def test_product_overview_is_not_browser_cached() -> None:
    with patch.object(main, "build_product_overview_response", return_value={"projects": []}):
        response = TestClient(main.app).get("/api/product/overview")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_environment_status_is_not_browser_cached() -> None:
    with patch.object(main, "detect_environments", return_value={"local_python": {"available": True}}):
        response = TestClient(main.app).get("/api/environments")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_product_overview_payload_has_freshness_timestamp() -> None:
    with (
        patch.object(main, "get_llm_settings", return_value={}),
        patch.object(main, "build_project_list_response", return_value=[]),
        patch.object(main, "list_auto_workflow_jobs", return_value={}),
        patch.object(main, "list_delivery_batch_jobs", return_value={}),
        patch.object(main, "list_delivery_package_batches", return_value=[]),
        patch.object(main, "load_capacity_settings", return_value={}),
        patch.object(main, "build_experience_center", return_value={}),
        patch.object(main, "list_capacity_autotune_events", return_value=[]),
        patch.object(main, "build_growth_metrics", return_value={}),
        patch.object(main, "build_trust_center", return_value={}),
        patch.object(main, "list_trust_report_exports", return_value=[]),
        patch.object(main, "list_repair_campaigns", return_value=[]),
        patch.object(main, "list_templates", return_value=[]),
    ):
        payload = main.build_product_overview_response()

    assert payload["generated_at"]
    assert payload["projects"] == []


def test_progress_polling_hint_is_fast_only_while_active() -> None:
    assert main.progress_poll_after_ms("running") < main.progress_poll_after_ms("success")
    assert main.progress_poll_after_ms("queued") == 700
    assert main.progress_poll_after_ms("running", 45) > main.progress_poll_after_ms("running", 0)
    assert main.progress_poll_after_ms("running", 120) > main.progress_poll_after_ms("running", 45)
    assert main.progress_poll_after_ms("failed") == 1600


def test_progress_live_quiet_seconds_reads_stream_status() -> None:
    progress = {"live_stream": {"quiet_seconds": "46"}}

    assert main.progress_live_quiet_seconds(progress) == 46
    assert main.progress_live_quiet_seconds({}) == 0


def test_progress_payload_gets_refresh_timestamp() -> None:
    payload = main.mark_progress_refreshed({"status": "running"})

    assert payload["status"] == "running"
    assert payload["refreshed_at"]


if __name__ == "__main__":
    test_product_overview_is_not_browser_cached()
    test_environment_status_is_not_browser_cached()
    test_product_overview_payload_has_freshness_timestamp()
    test_progress_polling_hint_is_fast_only_while_active()
    test_progress_live_quiet_seconds_reads_stream_status()
    test_progress_payload_gets_refresh_timestamp()
    print("api_cache_headers_tests_ok")
