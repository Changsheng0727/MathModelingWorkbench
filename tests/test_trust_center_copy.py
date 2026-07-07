from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.trust_center import build_trust_center
from app.services.trust_export import build_attestation, render_trust_markdown


def test_empty_quality_gate_copy_is_plain_language() -> None:
    center = build_trust_center([])

    assert center["label"] == "暂无质检数据"
    assert "信任" not in center["summary"]


def test_risky_quality_gate_copy_avoids_trust_jargon() -> None:
    center = build_trust_center(
        [
            {
                "id": "p1",
                "name": "示例项目",
                "auto_workflow_status": "failed",
                "last_failure_diagnosis": {"suggested_action": "继续生成并修复。"},
            }
        ]
    )

    assert center["label"] in {"交付存在风险", "交付阻断"}
    assert "交付质检评分" in center["summary"]


def test_quality_export_copy_is_delivery_focused() -> None:
    center = build_trust_center([])
    markdown = render_trust_markdown({"generated_at": "now", "trust": center, "attestation": build_attestation(center)})

    assert "Delivery Quality" in markdown
    assert "Trust status" not in markdown


if __name__ == "__main__":
    test_empty_quality_gate_copy_is_plain_language()
    test_risky_quality_gate_copy_avoids_trust_jargon()
    test_quality_export_copy_is_delivery_focused()
    print("trust_center_copy_tests_ok")
