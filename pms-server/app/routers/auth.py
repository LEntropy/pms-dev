import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.security import (
    verify_password, hash_password,
    create_access_token, create_refresh_token,
    decode_token,
)
from app.core.redis import get_redis, refresh_token_key
from app.core.deps import get_current_user
from app.core.exceptions import UnauthorizedError, ConflictError
from app.models.user import User
from app.models.audit import AuditLog
from app.schemas.auth import (
    LoginRequest, TokenResponse, RefreshRequest,
    MeResponse, UserCreateRequest,
)
from app.config import settings
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise UnauthorizedError("Invalid credentials")

    access_token = create_access_token(user.id, user.role)
    refresh_token, jti = create_refresh_token(user.id)

    redis = await get_redis()
    expire_seconds = settings.jwt_refresh_token_expire_days * 86400
    await redis.setex(refresh_token_key(jti), expire_seconds, user.id)

    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        actor_type="user",
        actor_id=user.id,
        action="auth.login",
        ip_address=request.client.host if request.client else None,
    ))
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    jti = payload.get("jti")
    user_id = payload.get("sub")

    redis = await get_redis()
    stored = await redis.get(refresh_token_key(jti))
    if not stored or stored != user_id:
        raise UnauthorizedError("Refresh token revoked or expired")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found")

    # Rotate: revoke old, issue new
    await redis.delete(refresh_token_key(jti))

    access_token = create_access_token(user.id, user.role)
    new_refresh, new_jti = create_refresh_token(user.id)

    expire_seconds = settings.jwt_refresh_token_expire_days * 86400
    await redis.setex(refresh_token_key(new_jti), expire_seconds, user.id)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout")
async def logout(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload and payload.get("type") == "refresh":
        jti = payload.get("jti")
        redis = await get_redis()
        await redis.delete(refresh_token_key(jti))
    return {"message": "Logged out"}


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)):
    return MeResponse.model_validate(user)


@router.post("/users", response_model=MeResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in ("superadmin", "admin"):
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError()

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise ConflictError("Email already registered")

    user = User(
        id=str(uuid.uuid4()),
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        role=body.role,
        organization_id=body.organization_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return MeResponse.model_validate(user)
