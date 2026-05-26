"""MinIO 파일 업로드/다운로드 서비스."""
import hashlib
import io
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from app.config import settings

_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


async def upload_patch(file_data: bytes, object_name: str) -> tuple[str, str, int]:
    """
    MinIO에 패치 파일을 업로드합니다.
    Returns (object_name, sha256_hex, file_size_bytes)
    """
    client = get_minio()
    sha256 = hashlib.sha256(file_data).hexdigest()
    size = len(file_data)

    client.put_object(
        settings.minio_bucket_patches,
        object_name,
        io.BytesIO(file_data),
        length=size,
        content_type="application/octet-stream",
    )

    return object_name, sha256, size


def get_presigned_download_url(object_name: str) -> str:
    """에이전트가 직접 파일을 내려받을 수 있는 서명된 URL을 발급합니다."""
    client = get_minio()
    url = client.presigned_get_object(
        settings.minio_bucket_patches,
        object_name,
        expires=timedelta(seconds=settings.minio_presigned_url_expire_seconds),
    )
    return url


def delete_patch_file(object_name: str) -> None:
    client = get_minio()
    try:
        client.remove_object(settings.minio_bucket_patches, object_name)
    except S3Error:
        pass
