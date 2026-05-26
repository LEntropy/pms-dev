"""
에이전트 코드 서명 검증.
서버 공개키(PEM)로 패치/에이전트 바이너리 서명을 검증한다.
에이전트 설치 시 공개키를 번들하고, 설치 전 반드시 서명을 검증한다.
"""
import base64
import hashlib
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# 번들된 공개키 경로 (에이전트 설치 디렉토리 기준)
_DEFAULT_PUBLIC_KEY = Path(__file__).parent.parent / "keys" / "server_public.pem"


def verify_file_signature(file_path: str, signature_b64: str, public_key_path: str | None = None) -> bool:
    """
    파일을 SHA-256 해시한 뒤 RSA 공개키로 서명을 검증한다.
    서명이 없거나(signature_b64 == None) 공개키가 없으면 경고 후 통과.
    """
    if not signature_b64:
        logger.warning("No signature provided for %s — skipping verification (allow)", file_path)
        return True

    key_path = public_key_path or str(_DEFAULT_PUBLIC_KEY)
    if not os.path.exists(key_path):
        logger.warning("Public key not found at %s — skipping signature check (allow)", key_path)
        return True

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.exceptions import InvalidSignature

        with open(file_path, "rb") as f:
            file_bytes = f.read()
        digest = hashlib.sha256(file_bytes).digest()

        with open(key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())

        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, digest, padding.PKCS1v15(), hashes.Prehashed(hashes.SHA256()))
        logger.info("Signature verified OK for %s", file_path)
        return True
    except Exception as exc:
        logger.error("Signature verification FAILED for %s: %s", file_path, exc)
        return False


def save_server_public_key(pem_text: str) -> None:
    """서버에서 받은 공개키를 로컬에 저장한다 (최초 등록 시 1회)."""
    key_dir = _DEFAULT_PUBLIC_KEY.parent
    key_dir.mkdir(parents=True, exist_ok=True)
    _DEFAULT_PUBLIC_KEY.write_text(pem_text, encoding="utf-8")
    logger.info("Server public key saved to %s", _DEFAULT_PUBLIC_KEY)
