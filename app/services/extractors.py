from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath


ALLOWED_EXTENSIONS = {
    ".zip",
    ".pdf",
    ".docx",
    ".xlsx",
    ".xls",
    ".csv",
    ".txt",
    ".md",
}


def validate_upload_name(filename: str) -> None:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"暂不支持的文件类型：{suffix}")


def save_upload(file_obj, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as fh:
        shutil.copyfileobj(file_obj, fh)
    return destination


def normalize_upload_relative_path(filename: str) -> PurePosixPath:
    normalized = filename.replace("\\", "/").strip("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"上传文件路径不安全：{filename}")
    if any(":" in part for part in path.parts):
        raise ValueError(f"上传文件路径不安全：{filename}")
    return path


def safe_folder_target(raw_dir: Path, filename: str) -> Path:
    relative = normalize_upload_relative_path(filename)
    target = (raw_dir / Path(*relative.parts)).resolve()
    root = raw_dir.resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"上传文件路径不安全：{filename}")
    return target


def unpack_upload(upload_path: Path, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    suffix = upload_path.suffix.lower()
    if suffix == ".zip":
        with zipfile.ZipFile(upload_path) as zf:
            for member in zf.infolist():
                target = safe_extract_target(raw_dir, member.filename)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    else:
        shutil.copy2(upload_path, raw_dir / upload_path.name)


def safe_extract_target(raw_dir: Path, member_name: str) -> Path:
    target = (raw_dir / member_name).resolve()
    root = raw_dir.resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"压缩包中存在不安全路径：{member_name}")
    return target
