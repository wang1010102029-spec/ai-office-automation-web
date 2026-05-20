from __future__ import annotations

import hashlib
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S_%f"


def timestamp_string(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime(DEFAULT_TIMESTAMP_FORMAT)


def normalize_filename(name: str, fallback: str = "file") -> str:
    candidate = Path(name).name.strip().replace("\\", "_").replace("/", "_")
    candidate = re.sub(r"\s+", "_", candidate)
    candidate = re.sub(r"[^\w.\-\u4e00-\u9fff]+", "_", candidate, flags=re.UNICODE)
    candidate = re.sub(r"_+", "_", candidate).strip("._")
    return candidate or fallback


def build_timestamped_filename(original_name: str, suffix: str, prefix: str | None = None) -> str:
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    safe_name = normalize_filename(original_name)
    stem = Path(safe_name).stem or "output"
    base = normalize_filename(prefix or stem, fallback="output")
    return f"{base}_{timestamp_string()}{suffix}"


def file_signature(data: bytes, filename: str | None = None) -> str:
    digest = hashlib.sha256()
    if filename:
        digest.update(normalize_filename(filename).encode("utf-8", errors="ignore"))
        digest.update(b"\0")
    digest.update(data)
    return digest.hexdigest()


def suffix_lower(filename: str) -> str:
    return Path(normalize_filename(filename)).suffix.lower()


def decode_text(data: bytes, encodings: Iterable[str] | None = None) -> str:
    candidates = encodings or ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1")
    for encoding in candidates:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def uploaded_file_bytes(uploaded_file) -> bytes:
    return uploaded_file.getvalue()


@contextmanager
def temporary_directory(prefix: str = "ai_office_") -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        yield Path(temp_dir)
