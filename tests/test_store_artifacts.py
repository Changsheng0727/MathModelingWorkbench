from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.store import build_artifact_status, primary_output_path, summarize_artifact_status


def test_support_zip_is_not_counted_as_generated_output() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        statuses = build_artifact_status(root, {})
        summary = summarize_artifact_status(statuses)

    assert summary["total"] == 0
    assert summary["available"] == 0
    assert primary_output_path(statuses) == ""


def test_primary_output_uses_existing_generated_file() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        target = root / "paper" / "main.pdf"
        target.parent.mkdir()
        target.write_text("pdf", encoding="utf-8")
        statuses = build_artifact_status(root, {"paper_pdf": "paper/main.pdf"})
        summary = summarize_artifact_status(statuses)

    assert summary["total"] == 1
    assert summary["available"] == 1
    assert summary["missing"] == 0
    assert primary_output_path(statuses) == "paper/main.pdf"


if __name__ == "__main__":
    test_support_zip_is_not_counted_as_generated_output()
    test_primary_output_uses_existing_generated_file()
    print("store_artifacts_tests_ok")
