"""
PMS Agent main loop.
Runs as a system service (Windows Service or Linux systemd).
"""
import logging
import platform
import socket
import sys
import time
import uuid
from datetime import datetime, timezone

from agent.api_client import PMSClient
from agent.config import AgentConfig, CONFIG_PATH
from agent.inventory import collect_software

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("pms-agent")

AGENT_VERSION = "0.1.0"


def get_platform_info() -> dict:
    sys_platform = platform.system().lower()
    return {
        "hostname": socket.gethostname(),
        "platform": "windows" if sys_platform == "windows" else "linux",
        "os_name": platform.system() + " " + platform.release(),
        "os_version": platform.version(),
        "arch": platform.machine(),
        "agent_version": AGENT_VERSION,
    }


def enroll(config: AgentConfig, client: PMSClient) -> bool:
    if not config.enrollment_token:
        logger.error("No enrollment token configured. Set it in config.json.")
        return False

    info = get_platform_info()
    try:
        result = client.enroll({
            "enrollment_token": config.enrollment_token,
            **info,
        })
        config.agent_token = result["agent_token"]
        config.endpoint_id = result["endpoint_id"]
        config.enrollment_token = ""  # clear after use
        config.save()
        logger.info("Enrolled successfully. Endpoint ID: %s", config.endpoint_id)

        # 서버 공개키 저장 (서명 검증용)
        if result.get("server_public_key"):
            from agent.executor.verify import save_server_public_key
            save_server_public_key(result["server_public_key"])

        return True
    except Exception as exc:
        logger.error("Enrollment failed: %s", exc)
        return False


def send_heartbeat(config: AgentConfig, client: PMSClient) -> dict | None:
    try:
        payload = {
            "agent_version": AGENT_VERSION,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_metrics": _collect_metrics(),
            "pending_reboot": _has_pending_reboot(),
        }
        return client.heartbeat(payload)
    except Exception as exc:
        logger.warning("Heartbeat failed: %s", exc)
        return None


def send_inventory(config: AgentConfig, client: PMSClient):
    try:
        packages = collect_software()
        payload = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "software": [
                {
                    "raw_name": p.raw_name,
                    "version": p.version,
                    "install_path": p.install_path,
                    "vendor": p.vendor,
                }
                for p in packages
            ],
        }
        client.submit_inventory(payload)
        logger.info("Inventory submitted: %d packages", len(packages))
    except Exception as exc:
        logger.warning("Inventory submission failed: %s", exc)


def process_tasks(config: AgentConfig, client: PMSClient):
    import tempfile
    import os
    from agent.executor import installer, rollback

    tasks = client.get_tasks()
    for task in tasks:
        task_id = task["task_id"]
        task_type = task["task_type"]
        payload = task.get("payload", {})

        logger.info("Processing task %s (type: %s)", task_id, task_type)

        if task_type == "inventory_now":
            send_inventory(config, client)
            client.update_task_status(task_id, {"status": "success"})
            continue

        if task_type == "patch_install":
            download_url = payload.get("download_url")
            file_hash = payload.get("file_hash_sha256")
            if not download_url or not file_hash:
                client.update_task_status(task_id, {"status": "failed", "error_message": "Missing download URL or hash"})
                continue

            client.update_task_status(task_id, {"status": "downloading"})

            tmp_file = os.path.join(tempfile.gettempdir(), f"pms_{task_id}")

            # 델타 패치 지원: delta_download_url이 있으면 델타 방식으로 다운로드
            delta_url = payload.get("delta_download_url")
            delta_hash = payload.get("delta_hash_sha256")
            base_file = payload.get("base_file_path")  # 에이전트 측에 이전 파일이 있으면

            if delta_url and delta_hash and base_file and os.path.exists(base_file):
                import asyncio
                from agent.executor.delta import download_and_apply_delta
                ok = asyncio.run(download_and_apply_delta(
                    base_path=base_file,
                    delta_url=delta_url,
                    delta_hash=delta_hash,
                    output_path=tmp_file,
                    new_hash=file_hash,
                    bandwidth_limit_kbps=payload.get("bandwidth_limit_kbps"),
                ))
            else:
                ok = client.download_file(
                    download_url, tmp_file, file_hash,
                    bandwidth_kbps=payload.get("bandwidth_limit_kbps"),
                )

            if not ok:
                client.update_task_status(task_id, {"status": "failed", "error_message": "Download or hash verification failed"})
                continue

            # 서명 검증 (signature가 페이로드에 있으면 반드시 통과해야 설치)
            from agent.executor.verify import verify_file_signature
            signature = payload.get("file_signature")
            if not verify_file_signature(tmp_file, signature):
                try:
                    os.unlink(tmp_file)
                except Exception:
                    pass
                client.update_task_status(task_id, {"status": "failed", "error_message": "Signature verification failed"})
                continue

            snapshot_id = rollback.create_snapshot()
            client.update_task_status(task_id, {"status": "installing", "rollback_snapshot_id": snapshot_id})

            success, exit_code = installer.install(
                tmp_file,
                pre_script=payload.get("pre_install_script"),
                post_script=payload.get("post_install_script"),
            )
            try:
                os.unlink(tmp_file)
            except Exception:
                pass

            if success:
                client.update_task_status(task_id, {"status": "success", "exit_code": exit_code, "rollback_snapshot_id": snapshot_id})
            else:
                if snapshot_id:
                    rollback.restore_snapshot(snapshot_id)
                client.update_task_status(task_id, {"status": "failed", "exit_code": exit_code})

        elif task_type == "patch_rollback":
            snapshot_id = payload.get("rollback_snapshot_id")
            if snapshot_id and rollback.restore_snapshot(snapshot_id):
                client.update_task_status(task_id, {"status": "rolled_back"})
            else:
                client.update_task_status(task_id, {"status": "failed", "error_message": "Rollback failed"})

        elif task_type == "agent_upgrade":
            import asyncio
            from agent.executor.upgrade import run_upgrade

            client.update_task_status(task_id, {"status": "downloading"})
            try:
                asyncio.run(run_upgrade(
                    download_url=payload["download_url"],
                    file_hash_sha256=payload["file_hash_sha256"],
                    version=payload["version"],
                    bandwidth_limit_kbps=payload.get("bandwidth_limit_kbps"),
                ))
                # run_upgrade replaces the process; this line is only reached on failure
                client.update_task_status(task_id, {"status": "success"})
            except Exception as exc:
                logger.error("Agent upgrade failed: %s", exc)
                client.update_task_status(task_id, {"status": "failed", "error_message": str(exc)})

        else:
            logger.warning("Unknown task type: %s", task_type)
            client.update_task_status(task_id, {"status": "skipped"})


def _collect_metrics() -> dict:
    try:
        import psutil
        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_free_gb": psutil.disk_usage("/").free / 1e9,
        }
    except ImportError:
        return {}


def _has_pending_reboot() -> bool:
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager")
            winreg.QueryValueEx(key, "PendingFileRenameOperations")
            return True
        except OSError:
            return False
    return False


def run():
    config = AgentConfig.load()

    with PMSClient(config) as client:
        if not config.agent_token:
            if not enroll(config, client):
                sys.exit(1)

        last_inventory = 0.0
        logger.info("PMS Agent started. Server: %s", config.server_url)

        while True:
            heartbeat_result = send_heartbeat(config, client)

            now = time.monotonic()
            if now - last_inventory >= config.inventory_interval:
                send_inventory(config, client)
                last_inventory = now

            if heartbeat_result and heartbeat_result.get("has_pending_tasks"):
                process_tasks(config, client)

            time.sleep(config.heartbeat_interval)


if __name__ == "__main__":
    run()
