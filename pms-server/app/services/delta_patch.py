"""
델타 패치 생성 서비스 (bsdiff4).
기존 바이너리(base) + 새 바이너리(new) → 델타 패치 파일 생성.
에이전트는 델타 파일을 다운로드하고 base에 적용해 새 바이너리를 복원한다.
"""
import hashlib
import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def generate_delta(base_path: str, new_path: str, output_path: str) -> dict:
    """
    base → new 델타 파일을 output_path에 생성.
    Returns: {delta_path, delta_hash, base_hash, new_hash, reduction_pct}
    """
    try:
        import bsdiff4
    except ImportError:
        raise RuntimeError("bsdiff4 is not installed. Run: pip install bsdiff4")

    with open(base_path, "rb") as f:
        base_data = f.read()
    with open(new_path, "rb") as f:
        new_data = f.read()

    delta_data = bsdiff4.diff(base_data, new_data)

    with open(output_path, "wb") as f:
        f.write(delta_data)

    original_size = os.path.getsize(new_path)
    delta_size = len(delta_data)
    reduction = round((1 - delta_size / max(original_size, 1)) * 100, 1)

    logger.info(
        "Delta generated: base=%d new=%d delta=%d reduction=%.1f%%",
        len(base_data), len(new_data), delta_size, reduction,
    )

    return {
        "delta_path": output_path,
        "delta_hash": _sha256(output_path),
        "base_hash": _sha256(base_path),
        "new_hash": _sha256(new_path),
        "reduction_pct": reduction,
    }


async def upload_delta_for_patch(patch_id: str, base_file_path: str, new_file_path: str) -> dict:
    """
    기존 패치 파일(base)과 신규 파일(new)로 delta를 생성한 뒤 MinIO에 업로드하고
    patches 레코드의 delta_patch_path, delta_hash_sha256을 갱신한다.
    """
    from app.services.file_distribution import _get_minio_client
    from app.config import settings

    tmp_delta = tempfile.mktemp(suffix=".patch")
    try:
        result = generate_delta(base_file_path, new_file_path, tmp_delta)

        client = _get_minio_client()
        object_name = f"deltas/{patch_id}.patch"
        client.fput_object(
            settings.minio_bucket_patches,
            object_name,
            tmp_delta,
            content_type="application/octet-stream",
        )

        return {
            "delta_object": object_name,
            "delta_hash": result["delta_hash"],
            "reduction_pct": result["reduction_pct"],
        }
    finally:
        try:
            os.unlink(tmp_delta)
        except Exception:
            pass
