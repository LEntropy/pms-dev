"""
LDAP/Active Directory 동기화 서비스.
조직(OU), 사용자(User), 엔드포인트 그룹을 AD에서 읽어 DB에 반영한다.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_ldap_conn():
    """ldap3 Connection 객체를 반환한다. LDAP 미설정 시 None."""
    from app.config import settings

    if not settings.ldap_url:
        return None

    try:
        import ldap3

        server = ldap3.Server(settings.ldap_url, get_info=ldap3.ALL)
        conn = ldap3.Connection(
            server,
            user=settings.ldap_bind_dn,
            password=settings.ldap_bind_password,
            authentication=ldap3.SIMPLE,
            auto_bind=True,
        )
        return conn
    except Exception as exc:
        logger.error("LDAP connection failed: %s", exc)
        return None


def _search(conn, base_dn: str, search_filter: str, attributes: list[str]) -> list[dict]:
    """LDAP 검색 결과를 dict 리스트로 반환."""
    import ldap3

    conn.search(
        search_base=base_dn,
        search_filter=search_filter,
        search_scope=ldap3.SUBTREE,
        attributes=attributes,
    )
    return [
        {attr: (entry[attr].value if hasattr(entry[attr], "value") else None)
         for attr in attributes}
        for entry in conn.entries
    ]


async def sync_users(db) -> dict[str, int]:
    """AD의 사용자 계정을 PMS users 테이블에 동기화한다."""
    from app.config import settings
    from app.models.user import User
    from app.core.security import hash_password
    from sqlalchemy import select
    import uuid

    conn = _get_ldap_conn()
    if not conn:
        logger.warning("LDAP not configured, skipping user sync")
        return {"synced": 0, "created": 0, "updated": 0}

    entries = _search(
        conn,
        settings.ldap_base_dn,
        settings.ldap_user_filter,
        ["sAMAccountName", "mail", "displayName", "department", "memberOf"],
    )

    created = updated = 0
    for entry in entries:
        email = entry.get("mail")
        if not email:
            continue

        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                id=str(uuid.uuid4()),
                email=email,
                display_name=entry.get("displayName") or email.split("@")[0],
                role="viewer",
                is_active=True,
                sso_provider="ldap",
                sso_subject=entry.get("sAMAccountName"),
            )
            db.add(user)
            created += 1
        else:
            user.display_name = entry.get("displayName") or user.display_name
            user.sso_subject = entry.get("sAMAccountName")
            db.add(user)
            updated += 1

    await db.commit()
    logger.info("LDAP user sync: created=%d updated=%d", created, updated)
    return {"synced": len(entries), "created": created, "updated": updated}


async def sync_organizations(db) -> dict[str, int]:
    """AD의 OU(조직단위)를 organizations 테이블에 동기화한다."""
    from app.config import settings
    from app.models.organization import Organization
    from sqlalchemy import select
    import uuid

    conn = _get_ldap_conn()
    if not conn:
        return {"synced": 0}

    entries = _search(
        conn,
        settings.ldap_base_dn,
        "(objectClass=organizationalUnit)",
        ["ou", "description", "distinguishedName"],
    )

    synced = 0
    for entry in entries:
        ou_name = entry.get("ou")
        if not ou_name:
            continue

        result = await db.execute(select(Organization).where(Organization.name == ou_name))
        org = result.scalar_one_or_none()
        if org is None:
            db.add(Organization(
                id=str(uuid.uuid4()),
                name=ou_name,
                description=entry.get("description"),
            ))
            synced += 1

    await db.commit()
    return {"synced": synced}


async def full_sync(db) -> dict:
    """사용자 + 조직 전체 동기화. 관리자 또는 Celery 스케줄에서 호출."""
    org_result = await sync_organizations(db)
    user_result = await sync_users(db)
    return {"organizations": org_result, "users": user_result}
