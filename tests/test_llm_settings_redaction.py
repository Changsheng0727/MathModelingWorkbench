from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


if __name__ == "__main__":
    test_redact_sensitive_text_masks_common_tokens()
    test_record_llm_test_result_persists_redacted_message()
    print("llm_settings_redaction_tests_ok")
