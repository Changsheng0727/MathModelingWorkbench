from pathlib import Path
import sys
from tempfile import TemporaryDirectory
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


def test_dependency_install_endpoint_starts_bootstrap_and_refreshes_environment() -> None:
    with (
        patch.object(main, "start_dependency_install", return_value={"started": True, "status": "checking"}),
        patch.object(main, "detect_environments", return_value={"dependency_summary": {"status": "installing"}}),
    ):
        response = TestClient(main.app).post("/api/environments/dependencies/install")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["install"]["started"] is True
    assert payload["environment"]["dependency_summary"]["status"] == "installing"


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


def test_project_summary_focus_prioritizes_missing_llm_settings() -> None:
    focus = main.build_project_summary_focus(
        {"total": 2, "failed": 1},
        [{"id": "p1", "auto_workflow_status": "failed"}],
        llm_settings={"configured": False},
    )

    assert focus["label"] == "先配置大模型接口"
    assert focus["guide_action"] == "focus_llm"
    assert focus["filter"] == "all"


def test_project_summary_focus_prioritizes_stale_llm_test() -> None:
    focus = main.build_project_summary_focus(
        {"total": 2, "failed": 1},
        [{"id": "p1", "auto_workflow_status": "failed"}],
        llm_settings={"configured": True, "connection_stale": True, "last_test_age_label": "2 天前"},
    )

    assert focus["guide_action"] == "test_llm"
    assert focus["action_label"] == "测试连接"
    assert focus["tone"] == "warning"
    assert focus["filter"] == "all"


def test_project_summary_focus_prioritizes_untested_llm_connection() -> None:
    focus = main.build_project_summary_focus(
        {"total": 2, "failed": 1},
        [{"id": "p1", "auto_workflow_status": "failed"}],
        llm_settings={"configured": True, "connection_status": "untested", "last_test": {}},
    )

    assert focus["guide_action"] == "test_llm"
    assert focus["action_label"] == "测试连接"
    assert focus["tone"] == "warning"
    assert focus["filter"] == "all"


def test_project_readiness_guides_untested_llm_before_auto_start() -> None:
    with TemporaryDirectory() as tmp:
        readiness = main.build_project_readiness(
            Path(tmp),
            metadata={"final_problem": {"id": "A"}},
            analysis={"recommended_problem": {"id": "A"}},
            llm_settings={"configured": True, "last_test": {}},
        )

    assert readiness["primary_action"]["id"] == "test_llm"
    assert readiness["phase"]["label"] == "测试连接"
    assert readiness["next_step"]["tone"] == "warning"


def test_project_readiness_guides_stale_llm_before_auto_start() -> None:
    with TemporaryDirectory() as tmp:
        readiness = main.build_project_readiness(
            Path(tmp),
            metadata={"final_problem": {"id": "A"}},
            analysis={"recommended_problem": {"id": "A"}},
            llm_settings={
                "configured": True,
                "connection_stale": True,
                "last_test_age_label": "2 天前",
                "last_test": {"ok": True, "tested_at": "2026-01-01T00:00:00"},
            },
        )

    assert readiness["primary_action"]["id"] == "test_llm"
    assert readiness["phase"]["label"] == "测试连接"
    assert readiness["checks"][2]["status"] == "pass"
    assert readiness["checks"][3]["status"] == "warning"


def test_batch_llm_preflight_requires_recent_successful_test() -> None:
    assert "先配置" in main.llm_batch_preflight_issue({"configured": False})
    assert "还没有成功连接测试记录" in main.llm_batch_preflight_issue(
        {"configured": True, "connection_status": "untested", "last_test": {}}
    )
    assert "重新测试" in main.llm_batch_preflight_issue(
        {
            "configured": True,
            "connection_stale": True,
            "last_test_age_label": "2 天前",
            "last_test": {"ok": True, "tested_at": "2026-01-01T00:00:00"},
        }
    )
    assert main.llm_batch_preflight_issue(
        {"configured": True, "last_test": {"ok": True, "tested_at": "2026-01-01T00:00:00"}}
    ) == ""


def test_auto_workflow_preflight_blocks_untested_llm_connection() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        main.save_json(artifacts / "analysis.json", {"recommended_problem": {"id": "A"}})

        preflight = main.build_auto_workflow_preflight(
            root,
            meta={"final_problem": {"id": "A"}},
            llm_settings={"configured": True, "connection_status": "untested", "last_test": {}},
        )

    assert preflight["can_start"] is False
    assert preflight["guide_action"] == "test_llm"
    assert preflight["action_label"] == "测试连接"
    assert "成功连接测试记录" in preflight["detail"]
    assert preflight["checked_at"]


def test_auto_workflow_preflight_exposes_recovery_action_for_missing_llm() -> None:
    with TemporaryDirectory() as tmp:
        preflight = main.build_auto_workflow_preflight(
            Path(tmp),
            meta={},
            llm_settings={"configured": False},
        )

    assert preflight["can_start"] is False
    assert preflight["guide_action"] == "focus_llm"
    assert preflight["action_label"] == "填写接口"


def test_auto_workflow_preflight_blocks_resume_when_llm_missing() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        main.save_json(artifacts / "analysis.json", {"recommended_problem": {"id": "A"}})

        preflight = main.build_auto_workflow_preflight(
            root,
            meta={"auto_workflow_status": "failed", "final_problem": {"id": "A"}},
            llm_settings={"configured": False},
        )

    assert preflight["primary_mode"] == "resume"
    assert preflight["can_resume"] is False
    assert preflight["label"] == "暂不能继续生成"
    assert preflight["guide_action"] == "focus_llm"
    assert "大模型" in preflight["resume_detail"]


def test_progress_resume_is_gated_by_preflight() -> None:
    progress = main.apply_auto_progress_preflight(
        {"status": "failed", "can_resume": True, "resume_hint": ""},
        {
            "primary_mode": "resume",
            "can_resume": False,
            "resume_detail": "请先重新测试大模型连接。",
        },
    )

    assert progress["can_resume"] is False
    assert progress["resume_blocked"] is True
    assert "重新测试" in progress["resume_hint"]


def test_auto_workflow_preflight_blocks_stale_llm_test() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        main.save_json(artifacts / "analysis.json", {"recommended_problem": {"id": "A"}})

        preflight = main.build_auto_workflow_preflight(
            root,
            meta={"final_problem": {"id": "A"}},
            llm_settings={
                "configured": True,
                "connection_stale": True,
                "last_test_age_label": "2 天前",
                "last_test": {"ok": True, "tested_at": "2026-01-01T00:00:00"},
            },
        )

    assert preflight["can_start"] is False
    assert preflight["status"] == "failed"
    assert preflight["guide_action"] == "test_llm"
    assert preflight["action_label"] == "测试连接"


def test_auto_workflow_preflight_exposes_problem_selection_action() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        artifacts = root / "artifacts"
        artifacts.mkdir()
        main.save_json(artifacts / "analysis.json", {"recommended_problem": {"id": "A"}})

        preflight = main.build_auto_workflow_preflight(
            root,
            meta={},
            llm_settings={"configured": True, "last_test": {"ok": True, "tested_at": "2026-01-01T00:00:00"}},
        )

    assert preflight["can_start"] is False
    assert preflight["guide_action"] == "open_problems"
    assert "A" in preflight["detail"]


def test_auto_batch_result_reports_all_skipped_as_failed() -> None:
    batch = main.build_auto_batch_result(
        2,
        [],
        [{"project_id": "p1", "reason": "未确认选题"}, {"project_id": "p2", "reason": "缺少分析"}],
        "auto",
    )

    assert batch["status"] == "failed"
    assert batch["submitted_count"] == 0
    assert batch["skipped_count"] == 2
    assert batch["actionable_skipped_count"] == 0
    assert "未提交任何项目" in batch["summary"]


def test_auto_batch_result_reports_partial_submission_as_warning() -> None:
    batch = main.build_auto_batch_result(
        2,
        [{"project_id": "p1"}],
        [{"project_id": "p2", "reason": "缺少分析", "guide_action": "analyze_project"}],
        "auto",
    )

    assert batch["status"] == "warning"
    assert batch["submitted_count"] == 1
    assert batch["skipped_count"] == 1
    assert batch["actionable_skipped_count"] == 1


def test_auto_batch_skip_includes_project_name() -> None:
    item = main.build_auto_batch_skip(
        "p1",
        "尚未确认最终选题。",
        {"name": "A题项目"},
        {"guide_action": "open_problems", "action_label": "去确认选题", "tone": "warning"},
    )

    assert item["project_id"] == "p1"
    assert item["project_name"] == "A题项目"
    assert item["reason"] == "尚未确认最终选题。"
    assert item["guide_action"] == "open_problems"
    assert item["action_label"] == "去确认选题"
    assert item["tone"] == "warning"


def test_auto_batch_skip_redacts_sensitive_reason() -> None:
    item = main.build_auto_batch_skip("p1", "Bearer " + "sk-" + "abcdefghijklmnopqrstuvwxyz123456")

    assert "sk-" not in item["reason"]
    assert "[REDACTED]" in item["reason"]


def test_auto_batch_skips_bad_metadata_and_submits_valid_project() -> None:
    with TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        bad = root / "bad"
        needs_problem = root / "needs_problem"
        good = root / "good"
        for project_root in [bad, needs_problem, good]:
            (project_root / "artifacts").mkdir(parents=True)
        (bad / "metadata.json").write_text("{", encoding="utf-8")
        (bad / "artifacts" / "analysis.json").write_text("{}", encoding="utf-8")
        (needs_problem / "metadata.json").write_text('{"id":"needs_problem","name":"待确认项目"}', encoding="utf-8")
        (needs_problem / "artifacts" / "analysis.json").write_text('{"recommended_problem":{"id":"B"}}', encoding="utf-8")
        (good / "metadata.json").write_text('{"id":"good","name":"可运行项目","final_problem":{"id":"A"}}', encoding="utf-8")
        (good / "artifacts" / "analysis.json").write_text('{"recommended_problem":{"id":"A"}}', encoding="utf-8")

        def fake_project_root(project_id: str) -> Path:
            return {"bad": bad, "needs_problem": needs_problem, "good": good}[project_id]

        with (
            patch.object(main, "project_root", side_effect=fake_project_root),
            patch.object(main, "get_llm_settings", return_value={"configured": True, "last_test": {"ok": True}}),
            patch.object(main, "start_auto_workflow_job", return_value={"project_id": "good", "job_id": "job-1"}),
            patch.object(main, "build_product_overview_response", return_value={"auto_jobs": {}, "projects": []}),
        ):
            payload = main.start_auto_workflow_batch(main.BatchAutoWorkflowPayload(project_ids=["bad", "needs_problem", "good"], mode="auto"))

    batch = payload["batch"]
    assert batch["status"] == "warning"
    assert batch["submitted_count"] == 1
    assert batch["skipped_count"] == 2
    assert batch["actionable_skipped_count"] == 1
    assert batch["skipped"][0]["project_id"] == "bad"
    assert "项目元数据无法读取" in batch["skipped"][0]["reason"]
    assert batch["skipped"][1]["project_name"] == "待确认项目"
    assert batch["skipped"][1]["guide_action"] == "open_problems"
    assert batch["skipped"][1]["action_label"] == "去确认选题"


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
    test_dependency_install_endpoint_starts_bootstrap_and_refreshes_environment()
    test_product_overview_payload_has_freshness_timestamp()
    test_project_summary_counts_workflow_signals()
    test_project_summary_focus_prioritizes_failures()
    test_project_summary_focus_flags_artifact_issues_before_urgent()
    test_project_summary_focus_prioritizes_missing_llm_settings()
    test_project_summary_focus_prioritizes_stale_llm_test()
    test_project_summary_focus_prioritizes_untested_llm_connection()
    test_project_readiness_guides_untested_llm_before_auto_start()
    test_project_readiness_guides_stale_llm_before_auto_start()
    test_batch_llm_preflight_requires_recent_successful_test()
    test_auto_workflow_preflight_blocks_untested_llm_connection()
    test_auto_workflow_preflight_exposes_recovery_action_for_missing_llm()
    test_auto_workflow_preflight_blocks_resume_when_llm_missing()
    test_progress_resume_is_gated_by_preflight()
    test_auto_workflow_preflight_blocks_stale_llm_test()
    test_auto_workflow_preflight_exposes_problem_selection_action()
    test_auto_batch_result_reports_all_skipped_as_failed()
    test_auto_batch_result_reports_partial_submission_as_warning()
    test_auto_batch_skip_includes_project_name()
    test_auto_batch_skip_redacts_sensitive_reason()
    test_auto_batch_skips_bad_metadata_and_submits_valid_project()
    test_progress_polling_hint_is_fast_only_while_active()
    test_progress_live_quiet_seconds_reads_stream_status()
    test_progress_payload_gets_refresh_timestamp()
    print("api_cache_headers_tests_ok")
