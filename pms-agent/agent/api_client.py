"""
HTTP client for PMS agent → server communication.
Handles JWT auth, automatic retry with exponential backoff, and optional CA pinning.
"""
import hashlib
import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from agent.config import AgentConfig

logger = logging.getLogger("pms-agent")

_RETRY_DELAYS = [5, 15, 30, 60]  # seconds between retries


class PMSClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self._base_url = config.server_url.rstrip("/") + "/api/v1"
        self._client: httpx.Client | None = None

    def _build_client(self) -> httpx.Client:
        kwargs: dict[str, Any] = {
            "timeout": httpx.Timeout(30.0),
            "headers": {"User-Agent": f"pms-agent/{self.config.agent_version}"},
        }
        if self.config.ca_cert_path:
            kwargs["verify"] = self.config.ca_cert_path
        return httpx.Client(**kwargs)

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _auth_headers(self) -> dict:
        if self.config.agent_token:
            return {"Authorization": f"Bearer {self.config.agent_token}"}
        return {}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        url = urljoin(self._base_url + "/", path.lstrip("/"))
        headers = {**self._auth_headers(), **kwargs.pop("headers", {})}

        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                logger.debug("Retry %d in %ds for %s %s", attempt, delay, method, path)
                time.sleep(delay)
            try:
                response = self.client.request(method, url, headers=headers, **kwargs)
                if response.status_code < 500:
                    return response
                logger.warning("Server error %d for %s %s", response.status_code, method, path)
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning("Network error for %s %s: %s", method, path, exc)

        raise RuntimeError(f"Failed after {len(_RETRY_DELAYS) + 1} attempts: {method} {path}")

    # --- Enrollment ---

    def enroll(self, payload: dict) -> dict:
        resp = self._request("POST", "/agent/enroll", json=payload)
        resp.raise_for_status()
        return resp.json()

    # --- Heartbeat ---

    def heartbeat(self, payload: dict) -> dict:
        resp = self._request("POST", "/agent/heartbeat", json=payload)
        resp.raise_for_status()
        return resp.json()

    # --- Tasks ---

    def get_tasks(self) -> list[dict]:
        resp = self._request("GET", "/agent/tasks")
        if resp.status_code == 200:
            return resp.json()
        return []

    def update_task_status(self, task_id: str, payload: dict) -> None:
        self._request("POST", f"/agent/tasks/{task_id}/status", json=payload)

    # --- Inventory ---

    def submit_inventory(self, payload: dict) -> None:
        resp = self._request("POST", "/agent/inventory", json=payload)
        if resp.status_code not in (200, 201):
            logger.warning("Inventory submission failed: %d", resp.status_code)

    # --- File download ---

    def download_file(self, url: str, dest_path: str, expected_sha256: str, bandwidth_kbps: int | None = None) -> bool:
        """Download a file with optional bandwidth throttling and SHA-256 verification."""
        chunk_size = 65536  # 64 KB default
        if bandwidth_kbps:
            # Throttle: sleep between chunks to stay within bandwidth limit
            bytes_per_second = bandwidth_kbps * 128  # kbps → bytes/s
            chunk_size = min(chunk_size, bytes_per_second // 4)

        sha256 = hashlib.sha256()
        try:
            with self.client.stream("GET", url, timeout=600) as resp:
                resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    chunk_start = time.monotonic()
                    bytes_written = 0
                    for chunk in resp.iter_bytes(chunk_size=chunk_size):
                        f.write(chunk)
                        sha256.update(chunk)
                        bytes_written += len(chunk)

                        if bandwidth_kbps:
                            elapsed = time.monotonic() - chunk_start
                            expected_time = bytes_written / (bandwidth_kbps * 128)
                            if expected_time > elapsed:
                                time.sleep(expected_time - elapsed)
        except Exception as exc:
            logger.error("Download failed from %s: %s", url, exc)
            return False

        actual = sha256.hexdigest()
        if actual != expected_sha256:
            logger.error("Hash mismatch: expected %s, got %s", expected_sha256, actual)
            return False

        return True

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
