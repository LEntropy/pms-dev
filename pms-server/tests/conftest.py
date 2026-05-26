"""공통 픽스처 — DB/Redis 없이 동작하는 테스트 환경."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# ── 환경변수 오버라이드 (DB/Redis 미연결 상태) ─────────────────────────
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pms:pms_secret@localhost:5432/pms")
os.environ.setdefault("REDIS_URL", "redis://:redis_secret@localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_testing_only")
os.environ.setdefault("JWT_PRIVATE_KEY_PATH", "keys/private.pem")
os.environ.setdefault("JWT_PUBLIC_KEY_PATH", "keys/public.pem")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "pms_minio")
os.environ.setdefault("MINIO_SECRET_KEY", "minio_secret")


@pytest.fixture(scope="session")
def rsa_keys(tmp_path_factory):
    """테스트용 RSA 키 쌍 생성."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key_dir = tmp_path_factory.mktemp("keys")
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_path = key_dir / "private.pem"
    public_path = key_dir / "public.pem"

    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return str(private_path), str(public_path)
