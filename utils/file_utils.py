"""파일 해시, 경로 관리 유틸리티."""

import hashlib
from pathlib import Path

from config import UPLOAD_DIR


def compute_file_hash(file_bytes: bytes) -> str:
    """파일 바이트의 SHA-256 해시 반환."""
    return hashlib.sha256(file_bytes).hexdigest()


def save_uploaded_file(file_bytes: bytes, filename: str) -> Path:
    """업로드된 파일을 uploads 디렉토리에 저장."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / filename
    # 동일 파일명 존재 시 숫자 접미사
    counter = 1
    while dest.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        dest = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    dest.write_bytes(file_bytes)
    return dest
