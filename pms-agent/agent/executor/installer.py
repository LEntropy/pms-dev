"""Silent patch installation for Windows (.exe/.msi) and Linux (dpkg/rpm/sh)."""
import logging
import os
import platform
import subprocess
from pathlib import Path

logger = logging.getLogger("pms-agent")


def install(file_path: str, pre_script: str | None = None, post_script: str | None = None) -> tuple[bool, int]:
    """
    Run pre-install script, install the patch, then post-install script.
    Returns (success, exit_code).
    """
    if pre_script:
        _run_script(pre_script, "pre-install")

    path = Path(file_path)
    suffix = path.suffix.lower()
    sys = platform.system()

    if sys == "Windows":
        exit_code = _install_windows(str(path), suffix)
    else:
        exit_code = _install_linux(str(path), suffix)

    success = exit_code in (0, 3010)  # 3010 = success, reboot required

    if post_script:
        _run_script(post_script, "post-install")

    return success, exit_code


def _install_windows(path: str, suffix: str) -> int:
    if suffix == ".msi":
        cmd = ["msiexec", "/i", path, "/qn", "/norestart", "ALLUSERS=1"]
    elif suffix == ".exe":
        cmd = [path, "/S", "/SILENT", "/VERYSILENT", "/NORESTART"]
    else:
        logger.error("Unsupported Windows installer format: %s", suffix)
        return 1

    return _run_cmd(cmd)


def _install_linux(path: str, suffix: str) -> int:
    if suffix == ".deb":
        cmd = ["dpkg", "-i", path]
    elif suffix == ".rpm":
        cmd = ["rpm", "-Uvh", path]
    elif suffix in (".sh", ""):
        os.chmod(path, 0o755)
        cmd = [path]
    else:
        logger.error("Unsupported Linux installer format: %s", suffix)
        return 1

    return _run_cmd(cmd)


def _run_cmd(cmd: list[str]) -> int:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.error("Install failed (exit %d): %s", result.returncode, result.stderr[:500])
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.error("Installation timed out: %s", cmd)
        return 1
    except Exception as exc:
        logger.error("Installation error: %s", exc)
        return 1


def _run_script(script_b64: str, label: str):
    import base64
    import tempfile
    try:
        script = base64.b64decode(script_b64).decode()
        with tempfile.NamedTemporaryFile(
            suffix=".bat" if platform.system() == "Windows" else ".sh",
            delete=False, mode="w"
        ) as f:
            f.write(script)
            tmp_path = f.name
        os.chmod(tmp_path, 0o755)
        subprocess.run(
            [tmp_path] if platform.system() != "Windows" else ["cmd", "/c", tmp_path],
            timeout=120,
        )
    except Exception as exc:
        logger.warning("%s script failed: %s", label, exc)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
