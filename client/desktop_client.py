from __future__ import annotations

import atexit
import logging
import os
import runpy
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


APP_TITLE = "数学建模竞赛智能工作台"
HOST = "127.0.0.1"
PREFERRED_PORT = int(os.environ.get("MODELING_WORKBENCH_PORT", "8765"))


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def log_client_event(message: str) -> None:
    try:
        root = project_root()
        log_dir = root / "data" / "client"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "client.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def find_available_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 50)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex((HOST, port)) != 0:
                return port
    raise RuntimeError("没有找到可用端口，请关闭占用本地端口的程序后重试。")


def wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"后端服务启动超时：{last_error}")


class BackendHandle:
    def __init__(self, server: object | None, thread: threading.Thread) -> None:
        self.server = server
        self.thread = thread
        self.pid = os.getpid()

    def poll(self) -> int | None:
        return None if self.thread.is_alive() else 0

    def terminate(self) -> None:
        if self.server is not None:
            setattr(self.server, "should_exit", True)

    def kill(self) -> None:
        self.terminate()

    def wait(self, timeout: float | None = None) -> None:
        self.thread.join(timeout=timeout)
        if self.thread.is_alive():
            raise TimeoutError("后端线程未能及时退出。")


def configure_runtime_paths(root: Path) -> None:
    os.environ.setdefault("MODELING_WORKBENCH_APP_ROOT", str(root))
    os.environ.setdefault("MODELING_WORKBENCH_DATA_ROOT", str(root / "data"))
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def bundled_resource(root: Path, name: str) -> Path | None:
    for candidate in [
        root / "app" / "resources" / name,
        root / "_internal" / "app" / "resources" / name,
    ]:
        if candidate.exists():
            return candidate
    return None


def start_dependency_bootstrap(root: Path) -> None:
    if os.environ.get("MODELING_WORKBENCH_SKIP_DEP_INSTALL") == "1":
        log_client_event("dependency bootstrap skipped by environment")
        return
    if os.name != "nt":
        return
    script = bundled_resource(root, "install_dependencies.ps1")
    if not script:
        log_client_event("dependency bootstrap script missing")
        return
    log_dir = root / "data" / "client"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "dependency_install.log"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-LogPath",
        str(log_path),
    ]
    try:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(command, cwd=root, creationflags=creationflags)
        log_client_event("dependency bootstrap started")
    except Exception:
        log_client_event("dependency bootstrap failed:\n" + traceback.format_exc())


def start_backend(port: int) -> BackendHandle:
    root = project_root()
    configure_runtime_paths(root)
    log_dir = root / "data" / "client"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "backend.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def run_server() -> None:
        try:
            import uvicorn

            config = uvicorn.Config(
                "app.main:app",
                host=HOST,
                port=port,
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
                logger = logging.getLogger(logger_name)
                if file_handler not in logger.handlers:
                    logger.addHandler(file_handler)
            server = uvicorn.Server(config)
            handle.server = server
            log_client_event(f"backend server.run starting port={port}")
            server.run()
            log_client_event("backend server.run exited")
        except Exception:
            detail = traceback.format_exc()
            log_client_event("backend thread crashed:\n" + detail)
            with log_path.open("a", encoding="utf-8") as handle_log:
                handle_log.write(detail)

    thread = threading.Thread(target=run_server, name="modeling-workbench-backend", daemon=True)
    handle = BackendHandle(None, thread)
    thread.start()

    def cleanup() -> None:
        if handle.poll() is None:
            handle.terminate()
            try:
                handle.wait(timeout=8)
            except TimeoutError:
                handle.kill()
        for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
            logger = logging.getLogger(logger_name)
            if file_handler in logger.handlers:
                logger.removeHandler(file_handler)
        file_handler.close()

    atexit.register(cleanup)
    return handle


def open_window(url: str) -> None:
    try:
        import webview  # type: ignore
    except ImportError:
        webbrowser.open(url)
        print("未安装 pywebview，已自动用浏览器打开。运行 `pip install pywebview` 后可使用桌面窗口。")
        print(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    window = webview.create_window(
        APP_TITLE,
        url,
        width=1280,
        height=860,
        min_size=(1100, 720),
    )
    webview.start(debug=False)
    if window:
        return


def main() -> int:
    log_client_event("client main starting")
    port = find_available_port(PREFERRED_PORT)
    log_client_event(f"selected port={port}")
    process = start_backend(port)
    url = f"http://{HOST}:{port}"
    try:
        wait_for_health(f"{url}/api/health")
        log_client_event("backend health check ok")
        start_dependency_bootstrap(project_root())
    except Exception:
        log_client_event("backend health check failed:\n" + traceback.format_exc())
        if process.poll() is None:
            process.terminate()
        raise
    open_window(url)
    return 0


def run_script_mode(argv: list[str]) -> int:
    if not argv:
        print("missing script path", file=sys.stderr)
        return 2
    root = project_root()
    configure_runtime_paths(root)
    script_path = Path(argv[0]).resolve()
    if not script_path.exists():
        print(f"script not found: {script_path}", file=sys.stderr)
        return 2
    cwd = Path.cwd().resolve()
    for path in [cwd, script_path.parent, root]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    sys.argv = [str(script_path), *argv[1:]]
    runpy.run_path(str(script_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mw-run-script":
        raise SystemExit(run_script_mode(sys.argv[2:]))
    raise SystemExit(main())
