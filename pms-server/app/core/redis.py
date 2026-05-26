from redis.asyncio import Redis, from_url
from app.config import settings

_redis: Redis | None = None


async def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = await from_url(settings.redis_url, decode_responses=True)
    return _redis


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


# Key helpers
def endpoint_online_key(endpoint_id: str) -> str:
    return f"pms:endpoint:online:{endpoint_id}"


def refresh_token_key(jti: str) -> str:
    return f"pms:refresh:{jti}"


def enrollment_token_key(token: str) -> str:
    return f"pms:enroll:{token}"
