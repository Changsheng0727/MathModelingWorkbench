from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.executor import summarize_dependencies


def test_dependency_summary_exposes_install_action_when_auto_install_is_available() -> None:
    summary = summarize_dependencies(
        {"missing": ["Pandoc", "XeLaTeX"]},
        {"available": True},
        {},
    )

    assert summary["status"] == "missing"
    assert summary["next_action"]["action"] == "install_dependencies"
    assert summary["next_action"]["button_label"] == "安装/重试"


def test_dependency_summary_exposes_refresh_action_when_manual_install_is_required() -> None:
    summary = summarize_dependencies(
        {"missing": ["Pandoc"]},
        {"available": False},
        {"status": "manual_required"},
    )

    assert summary["status"] == "manual_required"
    assert summary["next_action"]["action"] == "refresh_environment"
    assert summary["next_action"]["button_label"] == "刷新状态"


if __name__ == "__main__":
    test_dependency_summary_exposes_install_action_when_auto_install_is_available()
    test_dependency_summary_exposes_refresh_action_when_manual_install_is_required()
    print("executor_dependency_tests_ok")
