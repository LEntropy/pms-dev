"""Rollback support: Windows VSS snapshots and Linux package-state snapshots."""
import logging
import platform
import subprocess
import tempfile
import json
from pathlib import Path

logger = logging.getLogger("pms-agent")


def create_snapshot() -> str | None:
    """Create a pre-install snapshot. Returns snapshot ID or None on failure."""
    if platform.system() == "Windows":
        return _create_vss_snapshot()
    else:
        return _save_dpkg_state()


def restore_snapshot(snapshot_id: str) -> bool:
    """Restore from snapshot. Returns True on success."""
    if platform.system() == "Windows":
        return _restore_vss_snapshot(snapshot_id)
    else:
        return _restore_dpkg_state(snapshot_id)


# ── Windows VSS ──────────────────────────────────────────────────────────────

def _create_vss_snapshot() -> str | None:
    script = (
        "$vss = Get-WmiObject -List Win32_ShadowCopy; "
        "$result = $vss.Create('C:\\\\', 'ClientAccessible'); "
        "Write-Output $result.ShadowID"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NonInteractive", "-Command", script],
            text=True, timeout=60,
        ).strip()
        if out:
            logger.info("VSS snapshot created: %s", out)
            return out
    except Exception as exc:
        logger.warning("VSS snapshot creation failed: %s", exc)
    return None


def _restore_vss_snapshot(shadow_id: str) -> bool:
    # Requires reboot to take effect; mark restore intent and reboot
    restore_marker = Path(tempfile.gettempdir()) / "pms_vss_restore.json"
    restore_marker.write_text(json.dumps({"shadow_id": shadow_id}))
    logger.info("VSS restore scheduled for next boot: %s", shadow_id)
    return True


# ── Linux dpkg/rpm state ─────────────────────────────────────────────────────

def _save_dpkg_state() -> str | None:
    snap_path = Path(tempfile.gettempdir()) / f"pms_snap_{_timestamp()}.json"
    try:
        result = subprocess.run(
            ["dpkg", "--get-selections"], capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            result = subprocess.run(
                ["rpm", "-qa", "--queryformat", "%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n"],
                capture_output=True, text=True, timeout=30,
            )
        snap_path.write_text(json.dumps({"selections": result.stdout}))
        logger.info("Package state snapshot saved: %s", snap_path)
        return str(snap_path)
    except Exception as exc:
        logger.warning("Package state snapshot failed: %s", exc)
        return None


def _restore_dpkg_state(snapshot_path: str) -> bool:
    try:
        data = json.loads(Path(snapshot_path).read_text())
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(data["selections"])
            tmp = f.name
        result = subprocess.run(
            ["dpkg", "--set-selections"], stdin=open(tmp), timeout=300
        )
        subprocess.run(["apt-get", "dselect-upgrade", "-y"], timeout=600)
        return result.returncode == 0
    except Exception as exc:
        logger.error("Package state restore failed: %s", exc)
        return False


def _timestamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d%H%M%S")
