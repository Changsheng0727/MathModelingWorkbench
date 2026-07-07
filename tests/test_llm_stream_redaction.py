from pathlib import Path
import json
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_stream import LLMLiveStream, LLM_LIVE_STREAM_RELATIVE


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


if __name__ == "__main__":
    test_llm_live_stream_redacts_secrets_before_persisting()
    print("llm_stream_redaction_tests_ok")
