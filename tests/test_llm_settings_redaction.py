from pathlib import Path
import sys
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app.main as main
from app.services import llm_settings


def test_redact_sensitive_text_masks_common_tokens() -> None:
    api_key = "sk" + "-test_" + "abcdefghijklmnopqrstuvwxyz"
    jwt = "eyJ" + "abc.def.ghi"
    github_token = "github" + "_pat_" + "ABC123_secret"
    text = (
        f"api_key={api_key} "
        f"Bearer {jwt} "
        f"access{'_token'}={github_token}"
    )

    redacted = llm_settings.redact_sensitive_text(text)

    assert api_key not in redacted
    assert jwt not in redacted
    assert github_token not in redacted
    assert "[REDACTED]" in redacted


def test_normalize_api_key_accepts_common_pasted_formats() -> None:
    key = "sk-test_abcdefghijklmnopqrstuvwxyz"

    assert llm_settings.normalize_api_key(key) == key
    assert llm_settings.normalize_api_key(f"Bearer {key}") == key
    assert llm_settings.normalize_api_key(f"Authorization: Bearer {key}") == key
    assert llm_settings.normalize_api_key(f"OPENAI_API_KEY={key}") == key
    assert llm_settings.normalize_api_key(f'{{"api_key": "{key}"}}') == key
    assert llm_settings.normalize_api_key(f'"{key}"') == key


def test_normalize_base_url_accepts_common_pasted_formats() -> None:
    assert llm_settings.normalize_base_url("api.chshapi.org/v1") == "https://api.chshapi.org/v1"
    assert llm_settings.normalize_base_url('"api.openai.com"') == "https://api.openai.com/v1"
    assert llm_settings.normalize_base_url("https://api.chshapi.org/v1/chat/completions") == "https://api.chshapi.org/v1"
    assert llm_settings.normalize_base_url("BASE_URL=https://api.chshapi.org/v1") == "https://api.chshapi.org/v1"
    assert llm_settings.normalize_base_url('{"base_url": "api.chshapi.org/v1/chat/completions"}') == "https://api.chshapi.org/v1"


def test_record_llm_test_result_persists_redacted_message() -> None:
    original_path = llm_settings.SETTINGS_PATH
    api_key = "sk" + "-test_" + "abcdefghijklmnopqrstuvwxyz"
    jwt = "eyJ" + "abc.def.ghi"
    github_token = "github" + "_pat_" + "ABC123_secret"
    with TemporaryDirectory() as temp_dir:
        try:
            llm_settings.SETTINGS_PATH = Path(temp_dir) / "llm.json"
            settings = llm_settings.record_llm_test_result(
                False,
                "failed",
                f"provider rejected api_key={api_key}",
                {"label": f"Bearer {jwt}", "suggested_action": f"remove access{'_token'}={github_token}"},
            )
        finally:
            llm_settings.SETTINGS_PATH = original_path
    last_test = settings["last_test"]

    assert api_key not in last_test["message"]
    assert jwt not in last_test["diagnosis"]["label"]
    assert github_token not in last_test["diagnosis"]["suggested_action"]


def test_llm_settings_marks_stale_successful_test() -> None:
    original_path = llm_settings.SETTINGS_PATH
    with TemporaryDirectory() as temp_dir:
        try:
            llm_settings.SETTINGS_PATH = Path(temp_dir) / "llm.json"
            stale_time = (datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
            llm_settings.SETTINGS_PATH.write_text(
                '{"api_key":"sk-test_abcdefghijklmnopqrstuvwxyz","last_test":{"ok":true,"tested_at":"'
                + stale_time
                + '"}}',
                encoding="utf-8",
            )
            settings = llm_settings.get_llm_settings()
        finally:
            llm_settings.SETTINGS_PATH = original_path

    assert settings["connection_stale"] is True
    assert settings["connection_tone"] == "warning"
    assert settings["last_test_age_seconds"] >= 24 * 3600


def test_llm_test_endpoint_returns_redacted_error() -> None:
    original_path = llm_settings.SETTINGS_PATH
    api_key = "sk" + "-test_" + "abcdefghijklmnopqrstuvwxyz"
    jwt = "eyJ" + "abc.def.ghi"
    with TemporaryDirectory() as temp_dir:
        try:
            llm_settings.SETTINGS_PATH = Path(temp_dir) / "llm.json"
            with (
                patch.object(main, "get_llm_settings", return_value={"configured": True}),
                patch.object(main, "call_chat_completion", side_effect=RuntimeError(f"bad key {api_key}; Bearer {jwt}")),
            ):
                response = TestClient(main.app).post("/api/settings/llm/test")
        finally:
            llm_settings.SETTINGS_PATH = original_path

    payload = response.json()
    assert response.status_code == 200
    assert api_key not in payload["message"]
    assert jwt not in payload["message"]
    assert api_key not in str(payload.get("diagnosis", {}))
    assert jwt not in str(payload.get("diagnosis", {}))


def test_public_progress_payload_redacts_nested_strings() -> None:
    api_key = "sk" + "-test_" + "abcdefghijklmnopqrstuvwxyz"
    jwt = "eyJ" + "abc.def.ghi"
    github_token = "github" + "_pat_" + "ABC123_secret"
    payload = {
        "detail": f"solver failed with {api_key}",
        "steps": [{"title": f"retry Bearer {jwt}", "failure_diagnosis": {"evidence": f"access{'_token'}={github_token}"}}],
    }

    redacted = main.redact_public_payload(payload)
    text = str(redacted)

    assert api_key not in text
    assert jwt not in text
    assert github_token not in text
    assert "[REDACTED]" in text


if __name__ == "__main__":
    test_redact_sensitive_text_masks_common_tokens()
    test_normalize_api_key_accepts_common_pasted_formats()
    test_normalize_base_url_accepts_common_pasted_formats()
    test_record_llm_test_result_persists_redacted_message()
    test_llm_settings_marks_stale_successful_test()
    test_llm_test_endpoint_returns_redacted_error()
    test_public_progress_payload_redacts_nested_strings()
    print("llm_settings_redaction_tests_ok")
