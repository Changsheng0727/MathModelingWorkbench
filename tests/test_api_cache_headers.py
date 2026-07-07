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


def test_progress_polling_hint_is_fast_only_while_active() -> None:
    assert main.progress_poll_after_ms("running") < main.progress_poll_after_ms("success")
    assert main.progress_poll_after_ms("queued") == 700
    assert main.progress_poll_after_ms("failed") == 1600


def test_progress_payload_gets_refresh_timestamp() -> None:
    payload = main.mark_progress_refreshed({"status": "running"})

    assert payload["status"] == "running"
    assert payload["refreshed_at"]


if __name__ == "__main__":
    test_product_overview_is_not_browser_cached()
    test_progress_polling_hint_is_fast_only_while_active()
    test_progress_payload_gets_refresh_timestamp()
    print("api_cache_headers_tests_ok")
