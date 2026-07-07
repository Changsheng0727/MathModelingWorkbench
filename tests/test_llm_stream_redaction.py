from pathlib import Path
from datetime import datetime, timedelta
import json
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_stream import (
    LLMLiveStream,
    LLM_LIVE_STREAM_RELATIVE,
    LLM_STREAM_STALE_SECONDS,
    enrich_live_stream_status,
    load_llm_live_stream,
)


def test_llm_live_stream_redacts_secrets_before_persisting() -> None:
    api_key = "sk" + "-test_" + "abcdefghijklmnopqrstuvwxyz"
    jwt = "eyJ" + "abc.def.ghi"
    github_token = "github" + "_pat_" + "ABC123_secret"
    key_name = "access" + "_token"

    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        stream = LLMLiveStream(root, f"chan {api_key}", f"title {jwt}")
        stream.start(f"boot {key_name}={github_token}")
        stream.begin_request(f"ask {api_key}", 1, 1, None)
        stream.append_delta(f"model echoed {key_name}={github_token}")
        stream.finish_request("failed", "Bearer " + jwt)
        payload = json.loads((root / LLM_LIVE_STREAM_RELATIVE).read_text(encoding="utf-8"))

    text = json.dumps(payload, ensure_ascii=False)
    assert api_key not in text
    assert jwt not in text
    assert github_token not in text
    assert "[REDACTED]" in text


def test_load_llm_live_stream_marks_stale_running_stream() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        path = root / LLM_LIVE_STREAM_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "status": "running",
                    "channel": "auto_workflow",
                    "updated_at": (datetime.now() - timedelta(seconds=LLM_STREAM_STALE_SECONDS + 5)).isoformat(
                        timespec="seconds"
                    ),
                }
            ),
            encoding="utf-8",
        )
        payload = load_llm_live_stream(root)

    assert payload["is_stale"] is True
    assert payload["quiet_seconds"] >= LLM_STREAM_STALE_SECONDS
    assert payload["stale_action"]["id"] == "cancel_auto"
    assert "中断" in payload["stale_detail"]


def test_finished_stream_is_not_marked_stale() -> None:
    payload = enrich_live_stream_status(
        {
            "status": "success",
            "updated_at": (datetime.now() - timedelta(seconds=LLM_STREAM_STALE_SECONDS + 5)).isoformat(timespec="seconds"),
        }
    )

    assert payload["is_stale"] is False


def test_model_assistant_stale_stream_can_refresh() -> None:
    payload = enrich_live_stream_status(
        {
            "status": "running",
            "channel": "model_assistant",
            "updated_at": (datetime.now() - timedelta(seconds=LLM_STREAM_STALE_SECONDS + 5)).isoformat(timespec="seconds"),
        }
    )

    assert payload["is_stale"] is True
    assert payload["stale_action"]["id"] == "refresh_progress"
    assert "刷新" in payload["stale_detail"]


if __name__ == "__main__":
    test_llm_live_stream_redacts_secrets_before_persisting()
    test_load_llm_live_stream_marks_stale_running_stream()
    test_finished_stream_is_not_marked_stale()
    test_model_assistant_stale_stream_can_refresh()
    print("llm_stream_redaction_tests_ok")
