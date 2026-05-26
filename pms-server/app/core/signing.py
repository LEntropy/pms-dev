"""
에이전트 바이너리 / 패치 파일 RSA 서명 유틸.
서버가 서명하고, 에이전트가 공개 키로 검증한다.
"""
import base64
import hashlib
import logging

logger = logging.getLogger(__name__)


def sign_file(file_path: str, private_key_path: str) -> str:
    """파일을 RSA-PKCS1v15-SHA256으로 서명하고 base64 서명 문자열을 반환한다."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    with open(private_key_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    signature = private_key.sign(file_bytes, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode()


def verify_signature(file_path: str, signature_b64: str, public_key_path: str) -> bool:
    """공개 키로 파일 서명을 검증한다. 검증 실패 시 False 반환."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.exceptions import InvalidSignature

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        signature = base64.b64decode(signature_b64)

        with open(public_key_path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())

        public_key.verify(signature, file_bytes, padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, Exception) as exc:
        logger.warning("Signature verification failed: %s", exc)
        return False


def get_public_key_pem(public_key_path: str) -> str:
    """공개 키 PEM 문자열 반환 (에이전트 배포용)."""
    with open(public_key_path, "r") as f:
        return f.read()
