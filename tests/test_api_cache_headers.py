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
    assert payload["project_summary"]["total"] == 0
    assert payload["project_summary_focus"] == {}


def test_project_summary_counts_workflow_signals() -> None:
    summary = main.build_project_summary(
        [
            {
                "analysis_available": True,
                "readiness_next_step_urgency": "high",
                "readiness_bucket": "needs_action",
                "auto_workflow_status": "running",
            },
            {
                "readiness_bucket": "deliverable",
                "auto_workflow_status": "failed",
                "artifact_summary": {"missing": "1"},
            },
        ]
    )

    assert summary["total"] == 2
    assert summary["analyzed"] == 1
    assert summary["urgent"] == 1
    assert summary["needs_action"] == 1
    assert summary["running"] == 1
    assert summary["failed"] == 1
    assert summary["deliverable"] == 1
    assert summary["artifact_issue"] == 1


def test_project_summary_focus_prioritizes_failures() -> None:
    focus = main.build_project_summary_focus(
        {
            "total": 4,
            "failed": 1,
            "urgent": 2,
            "running": 1,
            "needs_action": 3,
        },
        [
            {
                "id": "p1",
                "name": "失败项目",
                "auto_workflow_status": "failed",
                "readiness_action_label": "继续修复",
                "readiness_action_hint": "从失败处继续生成。",
            },
            {"id": "p2", "name": "高优先级项目", "readiness_next_step_urgency": "high"},
        ],
    )

    assert focus["filter"] == "failed"
    assert focus["count"] == 1
    assert focus["tone"] == "failed"
    assert focus["project_id"] == "p1"
    assert focus["project_name"] == "失败项目"
    assert focus["project_next_step"] == "继续修复"
    assert focus["project_next_detail"] == "从失败处继续生成。"


def test_project_summary_focus_flags_artifact_issues_before_urgent() -> None:
    focus = main.build_project_summary_focus(
        {"total": 3, "artifact_issue": 1, "urgent": 2},
        [
            {"id": "p1", "readiness_next_step_urgency": "high"},
            {"id": "p2", "artifact_health_status": "warning"},
        ],
    )

    assert focus["filter"] == "artifact_issue"
    assert focus["project_id"] == "p2"


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
    test_project_summary_counts_workflow_signals()
    test_project_summary_focus_prioritizes_failures()
    test_project_summary_focus_flags_artifact_issues_before_urgent()
    test_progress_polling_hint_is_fast_only_while_active()
    test_progress_live_quiet_seconds_reads_stream_status()
    test_progress_payload_gets_refresh_timestamp()
    print("api_cache_headers_tests_ok")
