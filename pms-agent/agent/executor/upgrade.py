"""에이전트 자동 업그레이드 — 새 바이너리를 다운로드하고 현재 프로세스를 교체한다."""
import hashlib
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

CURRENT_EXE = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()


def _verify_hash(path: Path, expected: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        logger.error("Hash mismatch: expected %s, got %s", expected, actual)
        return False
    return True


async def run_upgrade(
    download_url: str,
    file_hash_sha256: str,
    version: str,
    bandwidth_limit_kbps: int | None = None,
) -> None:
    """
    1. 새 바이너리를 임시 파일로 다운로드
    2. SHA-256 검증
    3. 현재 실행파일 위치에 교체 (Windows는 배치 스크립트로 재시작)
    """
    from agent.api_client import PMSClient  # 다운로드에 대역폭 제어 포함

    tmp_dir = Path(tempfile.mkdtemp(prefix="pms_upgrade_"))
    suffix = ".exe" if platform.system() == "Windows" else ""
    new_bin = tmp_dir / f"pms-agent-{version}{suffix}"

    logger.info("Downloading agent %s from %s", version, download_url)

    client = PMSClient.__new__(PMSClient)  # 인증 없이 공개 URL 다운로드
    await client.download_file(
        download_url,
        str(new_bin),
        file_hash_sha256,
        bandwidth_limit_kbps=bandwidth_limit_kbps,
    )

    if not _verify_hash(new_bin, file_hash_sha256):
        raise RuntimeError("Agent binary hash verification failed")

    new_bin.chmod(0o755)
    logger.info("Replacing agent binary: %s → %s", new_bin, CURRENT_EXE)

    if platform.system() == "Windows":
        _replace_windows(new_bin)
    else:
        _replace_unix(new_bin)


def _replace_unix(new_bin: Path) -> None:
    """
    Unix: 현재 바이너리를 .old로 백업하고 새 바이너리로 교체한 뒤 execv로 재시작.
    """
    backup = CURRENT_EXE.with_suffix(".old")
    shutil.copy2(CURRENT_EXE, backup)
    shutil.move(str(new_bin), str(CURRENT_EXE))
    logger.info("Unix upgrade complete, restarting…")
    os.execv(str(CURRENT_EXE), sys.argv)


def _replace_windows(new_bin: Path) -> None:
    """
    Windows: CURRENT_EXE는 실행 중이라 직접 교체 불가.
    배치 스크립트로 딜레이 후 교체 + 재시작.
    """
    bat_path = new_bin.parent / "upgrade.bat"
    script = (
        "@echo off\n"
        "timeout /t 2 /nobreak >nul\n"
        f'copy /y "{new_bin}" "{CURRENT_EXE}"\n'
        f'start "" "{CURRENT_EXE}" {" ".join(sys.argv[1:])}\n'
        f'del "%~f0"\n'
    )
    bat_path.write_text(script, encoding="utf-8")
    logger.info("Windows upgrade: launching upgrade.bat and exiting")
    subprocess.Popen(["cmd.exe", "/c", str(bat_path)], close_fds=True)
    sys.exit(0)
