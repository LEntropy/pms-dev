"""
델타 패치 적용 모듈 (bsdiff4).
서버가 생성한 .patch 파일과 기존 바이너리를 결합해 새 버전 파일을 복원한다.
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


def apply_delta(base_path: str, delta_path: str, output_path: str) -> bool:
    """
    base 파일 + delta 파일 → 새 파일 복원.
    Returns True if successful.
    """
    try:
        import bsdiff4
    except ImportError:
        logger.error("bsdiff4 not installed. Install with: pip install bsdiff4")
        return False

    try:
        with open(base_path, "rb") as f:
            base_data = f.read()
        with open(delta_path, "rb") as f:
            delta_data = f.read()

        new_data = bsdiff4.patch(base_data, delta_data)

        with open(output_path, "wb") as f:
            f.write(new_data)

        logger.info(
            "Delta applied: base=%d delta=%d output=%d",
            len(base_data), len(delta_data), len(new_data),
        )
        return True
    except Exception as exc:
        logger.error("Delta apply failed: %s", exc)
        return False


async def download_and_apply_delta(
    base_path: str,
    delta_url: str,
    delta_hash: str,
    output_path: str,
    new_hash: str,
    bandwidth_limit_kbps: int | None = None,
) -> bool:
    """
    1. 델타 파일 다운로드 + 해시 검증
    2. 기존 파일에 적용
    3. 결과 파일 해시 검증
    """
    tmp_delta = tempfile.mktemp(suffix=".patch")
    try:
        from agent.api_client import PMSClient

        client = PMSClient.__new__(PMSClient)
        ok = client.download_file(
            delta_url,
            tmp_delta,
            delta_hash,
            bandwidth_kbps=bandwidth_limit_kbps,
        )
        if not ok:
            logger.error("Delta file download/hash verification failed")
            return False

        if not apply_delta(base_path, tmp_delta, output_path):
            return False

        actual = _sha256(output_path)
        if actual != new_hash:
            logger.error("Reconstructed file hash mismatch: expected %s got %s", new_hash, actual)
            os.unlink(output_path)
            return False

        logger.info("Delta patch applied and verified successfully")
        return True
    finally:
        try:
            os.unlink(tmp_delta)
        except Exception:
            pass
