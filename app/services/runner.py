from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.services.docx_export import export_word_document


def compile_latex(root: Path) -> dict[str, Any]:
    tex_dir = root / "paper"
    tex_file = tex_dir / "main.tex"
    if not tex_file.exists():
        raise FileNotFoundError("paper/main.tex 不存在")
    xelatex = shutil.which("xelatex")
    if not xelatex:
        raise FileNotFoundError("未找到 xelatex")

    logs = []
    success = True
    for index in range(2):
        result = subprocess.run(
            [xelatex, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
            cwd=tex_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            check=False,
        )
        logs.append(f"===== xelatex pass {index + 1} =====\n{result.stdout}\n{result.stderr}")
        if result.returncode != 0:
            success = False
            break

    log_path = root / "artifacts" / "latex_compile.log"
    log_path.write_text("\n\n".join(logs), encoding="utf-8")
    pdf_path = tex_dir / "main.pdf"
    payload = {
        "success": success and pdf_path.exists(),
        "log": "artifacts/latex_compile.log",
        "pdf": "paper/main.pdf" if pdf_path.exists() else "",
    }
    try:
        word_result = export_word_document(root)
        payload["docx"] = word_result.get("docx", "")
        payload["word_log"] = word_result.get("log", "")
        payload["word_success"] = bool(word_result.get("success"))
        payload["word_method"] = word_result.get("method", "")
    except Exception as exc:
        word_log = root / "artifacts" / "word_export.log"
        word_log.write_text(f"Word 导出失败：{type(exc).__name__}: {exc}", encoding="utf-8")
        payload["docx"] = ""
        payload["word_log"] = "artifacts/word_export.log"
        payload["word_success"] = False
        payload["word_error"] = f"{type(exc).__name__}: {exc}"
    return payload
