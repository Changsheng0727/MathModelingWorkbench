from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.executor as executor


def test_dependency_summary_exposes_install_action_when_auto_install_is_available() -> None:
    summary = executor.summarize_dependencies(
        {"missing": ["Pandoc", "XeLaTeX"]},
        {"available": True},
        {},
    )

    assert summary["status"] == "missing"
    assert summary["next_action"]["action"] == "install_dependencies"
    assert summary["next_action"]["button_label"] == "安装/重试"


def test_dependency_summary_exposes_refresh_action_when_manual_install_is_required() -> None:
    summary = executor.summarize_dependencies(
        {"missing": ["Pandoc"]},
        {"available": False},
        {"status": "manual_required"},
    )

    assert summary["status"] == "manual_required"
    assert summary["next_action"]["action"] == "refresh_environment"
    assert summary["next_action"]["button_label"] == "刷新状态"


def test_active_dependency_install_status_uses_generated_time_window() -> None:
    current = 100_000.0
    fresh = time_payload(current - 120)
    stale = time_payload(current - executor.DEPENDENCY_INSTALL_ACTIVE_SECONDS - 10)

    assert executor.dependency_install_is_active({"status": "installing", "generated_at": fresh}, now=current)
    assert not executor.dependency_install_is_active({"status": "installing", "generated_at": stale}, now=current)
    assert not executor.dependency_install_is_active({"status": "ready", "generated_at": fresh}, now=current)


def test_start_dependency_install_reuses_active_existing_status() -> None:
    active_status = {"status": "installing", "generated_at": time_payload(), "log": "existing.log"}
    with patch.object(executor, "load_dependency_install_status", return_value=active_status):
        result = executor.start_dependency_install()

    assert result["started"] is False
    assert result["existing"] is True
    assert result["status"] == "installing"


def time_payload(timestamp: float | None = None) -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(timestamp))


if __name__ == "__main__":
    test_dependency_summary_exposes_install_action_when_auto_install_is_available()
    test_dependency_summary_exposes_refresh_action_when_manual_install_is_required()
    test_active_dependency_install_status_uses_generated_time_window()
    test_start_dependency_install_reuses_active_existing_status()
    print("executor_dependency_tests_ok")
