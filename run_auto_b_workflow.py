from __future__ import annotations

import json
import sys
import traceback

from app.services.auto_workflow import run_auto_workflow
from app.services.store import load_json, project_root, save_json


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    project_id = "20260522-162622-62355bb2"
    root = project_root(project_id)
    meta = load_json(root / "metadata.json")
    if isinstance(meta.get("final_problem"), dict):
        meta["final_problem"]["reason"] = "User selected problem B; the automatic workflow must solve this problem."
    meta["paper_options"] = {"template_id": "builtin-default", "target_body_pages": None}
    save_json(root / "metadata.json", meta)
    try:
        report = run_auto_workflow(root, meta)
        print(
            json.dumps(
                {"ok": True, "overall_status": report.get("overall_status"), "root": str(root)},
                ensure_ascii=False,
                indent=2,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"{type(exc).__name__}: {exc}", "root": str(root)},
                ensure_ascii=False,
                indent=2,
            )
        )
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
