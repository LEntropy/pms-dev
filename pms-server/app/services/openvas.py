"""
OpenVAS / Greenbone Vulnerability Manager 연동 서비스.
GVM REST API를 통해 취약점 스캔 결과를 가져와 CVE-패치 매핑을 갱신한다.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class GVMClient:
    """Greenbone Vulnerability Manager REST API 클라이언트."""

    def __init__(self, base_url: str, username: str, password: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._token: str | None = None

    async def _authenticate(self) -> None:
        import httpx

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                f"{self.base_url}/gmp",
                content=f'<authenticate><credentials><username>{self.username}</username>'
                        f'<password>{self.password}</password></credentials></authenticate>',
                headers={"Content-Type": "application/xml"},
            )
            resp.raise_for_status()
            self._token = resp.cookies.get("GVM_Session")

    async def get_vulnerabilities(self, task_id: str | None = None) -> list[dict]:
        """스캔 결과에서 취약점 목록을 가져온다."""
        import httpx
        import xml.etree.ElementTree as ET

        if not self._token:
            await self._authenticate()

        params = {"type": "results", "filter": "severity>0"}
        if task_id:
            params["task_id"] = task_id

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.get(
                f"{self.base_url}/results",
                params=params,
                cookies={"GVM_Session": self._token or ""},
            )
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        vulns = []
        for result in root.findall(".//result"):
            cves = [ref.get("id", "") for ref in result.findall(".//ref[@type='cve']")]
            host = result.findtext("host/ip") or ""
            severity = result.findtext("severity") or "0"
            name = result.findtext("name") or ""
            vulns.append({
                "host": host,
                "name": name,
                "severity": float(severity),
                "cves": cves,
            })

        return vulns

    async def trigger_scan(self, target_ips: list[str]) -> str:
        """새 스캔 작업을 생성하고 task_id를 반환한다."""
        import httpx

        if not self._token:
            await self._authenticate()

        # 실제 GVM XML API로 target + task 생성 (여기서는 플레이스홀더)
        logger.info("OpenVAS scan triggered for %d hosts", len(target_ips))
        return "placeholder_task_id"


async def sync_cve_to_patches(db, vulnerabilities: list[dict]) -> int:
    """OpenVAS 결과의 CVE를 패치 테이블의 cve_ids에 반영한다."""
    from app.models.patch import Patch
    from sqlalchemy import select

    updated = 0
    for vuln in vulnerabilities:
        for cve in vuln["cves"]:
            result = await db.execute(
                select(Patch).where(Patch.cve_ids.contains([cve]))
            )
            for patch in result.scalars():
                logger.info("CVE %s matched patch %s", cve, patch.id)
                # 향후: 엔드포인트 IP → endpoint 매핑 후 compliance 재계산 트리거
                updated += 1

    return updated


async def run_full_scan_and_sync(db) -> dict:
    """
    1. 현재 활성 엔드포인트 IP 목록 수집
    2. OpenVAS 스캔 트리거
    3. 결과 → CVE 매핑 동기화
    """
    from app.config import settings
    from app.models.endpoint import Endpoint
    from sqlalchemy import select

    if not settings.openvas_url:
        logger.info("OpenVAS not configured, skipping scan")
        return {"status": "skipped"}

    result = await db.execute(
        select(Endpoint.ip_address).where(Endpoint.status == "active", Endpoint.ip_address != None)
    )
    ips = [row[0] for row in result]

    client = GVMClient(
        settings.openvas_url,
        settings.openvas_username,
        settings.openvas_password,
    )

    task_id = await client.trigger_scan(ips)
    # 스캔 완료까지 대기 후 결과 가져오기 (여기서는 즉시 호출)
    vulns = await client.get_vulnerabilities(task_id)
    synced = await sync_cve_to_patches(db, vulns)

    return {"scan_triggered": True, "hosts": len(ips), "vulnerabilities": len(vulns), "patches_matched": synced}
