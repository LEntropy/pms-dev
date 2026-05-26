"""
주기적 동기화 태스크 (Celery beat).
- LDAP/AD 사용자/조직 동기화 (1일 1회)
- OpenVAS 취약점 스캔 (주 1회)
"""
import asyncio
import logging

from app.tasks.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    name="app.tasks.sync_tasks.ldap_sync",
    queue="default",
)
def ldap_sync():
    """LDAP/AD → PMS DB 전체 동기화."""
    _run_async(_do_ldap_sync())


async def _do_ldap_sync():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.services.ldap_sync import full_sync

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        result = await full_sync(db)
        logger.info("LDAP sync completed: %s", result)

    await engine.dispose()


@celery_app.task(
    name="app.tasks.sync_tasks.openvas_scan",
    queue="default",
)
def openvas_scan():
    """OpenVAS 취약점 스캔 트리거 및 CVE 매핑 갱신."""
    _run_async(_do_openvas_scan())


async def _do_openvas_scan():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.services.openvas import run_full_scan_and_sync

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        result = await run_full_scan_and_sync(db)
        logger.info("OpenVAS scan completed: %s", result)

    await engine.dispose()
