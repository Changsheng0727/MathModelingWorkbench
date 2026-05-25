from __future__ import annotations

import contextlib
import ctypes
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

from app.config import APP_ROOT


_WINDOWS_SUBPROCESS_LOCK = threading.RLock()
WINDOWS_LOADER_FAILURES = {
    0xC0000135: "missing required DLL",
    0xC0000142: "DLL initialization failed",
    0xC000007B: "invalid executable or DLL architecture",
}


def find_external_command(name: str) -> str | None:
    return shutil.which(name, path=sanitized_subprocess_env().get("PATH"))


def run_external_command(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("env", sanitized_subprocess_env())
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with clean_windows_process_launch():
        return subprocess.run(command, **kwargs)


def popen_external_command(command: list[str], **kwargs: Any) -> subprocess.Popen[Any]:
    kwargs.setdefault("env", sanitized_subprocess_env())
    if os.name == "nt":
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with clean_windows_process_launch():
        return subprocess.Popen(command, **kwargs)


def sanitized_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    if os.name != "nt":
        return env

    internal_dirs = {normalize_path(path) for path in pyinstaller_internal_dirs() if path}
    parts = []
    seen = set()
    for raw_part in env.get("PATH", "").split(os.pathsep):
        part = raw_part.strip()
        if not part:
            continue
        normalized = normalize_path(Path(part))
        if normalized in internal_dirs:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        parts.append(part)
    env["PATH"] = os.pathsep.join(parts)

    # External tools should not inherit Python import settings from the bundled app.
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    return env


def pyinstaller_internal_dirs() -> list[Path]:
    paths: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass))
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths.extend([exe_dir, exe_dir / "_internal"])
    paths.extend([APP_ROOT, APP_ROOT / "_internal"])
    return paths


def normalize_path(path: Path) -> str:
    try:
        return str(path.resolve()).casefold()
    except Exception:
        return str(path).casefold()


@contextlib.contextmanager
def clean_windows_process_launch() -> Iterator[None]:
    if os.name != "nt":
        yield
        return

    with _WINDOWS_SUBPROCESS_LOCK:
        kernel32 = ctypes.windll.kernel32
        previous_error_mode = kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        restore_dll_dir = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
        try:
            kernel32.SetDllDirectoryW(None)
            yield
        finally:
            if restore_dll_dir:
                kernel32.SetDllDirectoryW(str(restore_dll_dir))
            kernel32.SetErrorMode(previous_error_mode)


def is_windows_loader_failure(returncode: int | None) -> bool:
    if returncode is None:
        return False
    return (int(returncode) & 0xFFFFFFFF) in WINDOWS_LOADER_FAILURES


def describe_returncode(returncode: int | None) -> str:
    if returncode is None:
        return "process did not return a code"
    normalized = int(returncode) & 0xFFFFFFFF
    reason = WINDOWS_LOADER_FAILURES.get(normalized)
    if reason:
        return f"exit code 0x{normalized:08X} ({reason})"
    return f"exit code {returncode}"
