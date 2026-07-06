from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.config import DATA_ROOT
from app.services.process_utils import describe_returncode, find_external_command, run_external_command


def python_script_command(script_path: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--mw-run-script", str(script_path)]
    return [sys.executable, "-X", "utf8", str(script_path)]


def detect_environments() -> dict[str, Any]:
    pandoc = detect_command(["pandoc", "--version"])
    xelatex = detect_command(["xelatex", "--version"])
    winget = detect_winget()
    dependency_install = load_dependency_install_status()
    required_dependencies = {
        "ready": bool(pandoc.get("available")) and bool(xelatex.get("available")),
        "missing": [
            name
            for name, item in [("Pandoc", pandoc), ("XeLaTeX", xelatex)]
            if not item.get("available")
        ],
    }
    return {
        "local_python": {
            "available": True,
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "pandoc": pandoc,
        "xelatex": xelatex,
        "winget": winget,
        "dependency_install": dependency_install,
        "required_dependencies": required_dependencies,
        "dependency_summary": summarize_dependencies(required_dependencies, winget, dependency_install),
        "docker": detect_command(["docker", "--version"], ["docker", "info"]),
        "wsl": detect_command(["wsl", "--version"]),
    }


def summarize_dependencies(required: dict[str, Any], winget: dict[str, Any], install: dict[str, Any]) -> dict[str, Any]:
    missing = [str(item) for item in required.get("missing", [])]
    install_status = str(install.get("status") or "")
    can_auto_install = bool(winget.get("available"))
    summary = {
        "status": "ready",
        "label": "导出依赖已就绪",
        "detail": "Word 导出和 LaTeX PDF 编译依赖均可用。",
        "missing": missing,
        "can_auto_install": can_auto_install,
        "install_status": install_status,
        "log": install.get("log", ""),
    }
    if not missing:
        return summary

    names = "、".join(missing)
    if install_status in {"checking", "installing"}:
        summary.update(
            {
                "status": "installing",
                "label": "正在准备导出依赖",
                "detail": f"正在处理 {names}，完成后可能需要重启软件再导出。",
            }
        )
    elif install_status == "partial":
        summary.update(
            {
                "status": "warning",
                "label": "依赖安装需复核",
                "detail": f"已尝试安装，但仍缺少 {names}；重启软件后若仍缺失，请手动安装。",
            }
        )
    elif install_status == "unreadable":
        summary.update(
            {
                "status": "warning",
                "label": "依赖状态不可读",
                "detail": f"缺少 {names}，且本地安装状态文件暂时不可读。",
            }
        )
    elif install_status == "manual_required" or not can_auto_install:
        summary.update(
            {
                "status": "manual_required",
                "label": "需要手动安装依赖",
                "detail": f"缺少 {names}，且未检测到 winget 自动安装能力。",
            }
        )
    else:
        summary.update(
            {
                "status": "missing",
                "label": "缺少导出依赖",
                "detail": f"缺少 {names}；客户端会尝试用 winget 自动下载，稍后可刷新状态。",
            }
        )
    return summary


def detect_winget() -> dict[str, Any]:
    found = detect_command(["winget", "--version"])
    if found.get("available") or os.name != "nt":
        return found
    candidate = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "winget.exe"
    if candidate.exists():
        return detect_command([str(candidate), "--version"])
    return found


def detect_command(version_cmd: list[str], health_cmd: list[str] | None = None) -> dict[str, Any]:
    command_name = version_cmd[0]
    executable = str(Path(command_name)) if Path(command_name).exists() else find_external_command(command_name)
    if not executable:
        return {"available": False, "reason": f"{command_name} not found"}
    try:
        version = run_external_command(
            [executable, *version_cmd[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return {"available": False, "executable": executable, "reason": f"{type(exc).__name__}: {exc}"}

    available = version.returncode == 0
    reason = version.stdout.strip() or version.stderr.strip() or describe_returncode(version.returncode)
    if health_cmd and available:
        try:
            health_executable = find_external_command(health_cmd[0]) or health_cmd[0]
            health = run_external_command(
                [health_executable, *health_cmd[1:]],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except Exception as exc:
            return {"available": False, "executable": executable, "detail": f"{type(exc).__name__}: {exc}"}
        available = health.returncode == 0
        if not available:
            reason = health.stderr.strip() or health.stdout.strip() or describe_returncode(health.returncode)
    return {"available": available, "executable": executable, "detail": reason}


def load_dependency_install_status() -> dict[str, Any]:
    status_path = DATA_ROOT / "client" / "dependency_status.json"
    if not status_path.exists():
        return {}
    try:
        import json

        payload = json.loads(status_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        return {"status": "unreadable", "error": f"{type(exc).__name__}: {exc}"}


def run_python_script(root: Path, script_relative: str, log_relative: str, timeout: int = 240) -> dict[str, Any]:
    script_path = (root / script_relative).resolve()
    if root.resolve() not in script_path.parents and script_path != root.resolve():
        raise ValueError("script path is outside the project directory")
    if not script_path.exists():
        raise FileNotFoundError(script_relative)

    log_path = root / log_relative
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    try:
        result = subprocess.run(
            python_script_command(script_path),
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        duration_seconds = round(time.perf_counter() - started, 3)
        log_path.write_text(
            "\n".join(
                [
                    "executor=local_python",
                    f"python={sys.executable}",
                    "returncode=timeout",
                    f"timeout_seconds={timeout}",
                    f"duration_seconds={duration_seconds}",
                    "===== STDOUT =====",
                    stdout,
                    "===== STDERR =====",
                    stderr,
                ]
            ),
            encoding="utf-8",
        )
        return {
            "success": False,
            "returncode": -1,
            "executor": "local_python",
            "log": log_relative.replace("\\", "/"),
            "error": f"timeout after {timeout} seconds",
            "duration_seconds": duration_seconds,
        }
    duration_seconds = round(time.perf_counter() - started, 3)
    log_path.write_text(
        "\n".join(
            [
                "executor=local_python",
                f"python={sys.executable}",
                f"returncode={result.returncode}",
                f"duration_seconds={duration_seconds}",
                "===== STDOUT =====",
                result.stdout,
                "===== STDERR =====",
                result.stderr,
            ]
        ),
        encoding="utf-8",
    )
    return {
        "success": result.returncode == 0,
        "returncode": result.returncode,
        "executor": "local_python",
        "log": log_relative.replace("\\", "/"),
        "duration_seconds": duration_seconds,
    }
