"""
Bootstrap script: create the initial superadmin account.
Usage:
  python seed.py --email admin@company.com --password changeme
"""
import argparse
import asyncio
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from app.config import settings
from app.core.security import hash_password, generate_rsa_keys
from app.database import Base
from app.models import User, Organization  # ensure all models are imported


async def seed(email: str, password: str, display_name: str):
    generate_rsa_keys()

    engine = create_async_engine(settings.database_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with Session() as session:
        existing = await session.execute(select(User).where(User.email == email))
        if existing.scalar_one_or_none():
            print(f"[skip] User already exists: {email}")
            await engine.dispose()
            return

        user = User(
            id=str(uuid.uuid4()),
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            role="superadmin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()
        print(f"[ok] Superadmin created: {email}  (id={user.id})")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PMS seed: create initial superadmin")
    parser.add_argument("--email", required=True, help="Admin email")
    parser.add_argument("--password", required=True, help="Admin password")
    parser.add_argument("--name", default="Administrator", help="Display name")
    args = parser.parse_args()

    asyncio.run(seed(args.email, args.password, args.name))
