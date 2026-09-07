"""Password hashing + DB user authentication."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Role, User, UserRole

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SEED_USERS: list[dict[str, str]] = [
    {
        "username": "Admin",
        "email": "admin@tams.local",
        "display_name": "Admin",
        "department": "IT",
    },
    {
        "username": "VishalBhor",
        "email": "vishalbhor@tams.local",
        "display_name": "VishalBhor",
        "department": "Engineering",
    },
    {
        "username": "ShwetaPawar",
        "email": "shwetapawar@tams.local",
        "display_name": "ShwetaPawar",
        "department": "Engineering",
    },
]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return pwd_context.verify(plain, password_hash)
    except Exception:
        return False


def create_access_token(*, subject: str, role: str, user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
    payload = {
        "sub": subject,
        "role": role,
        "uid": user_id,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def ensure_auth_schema(session: AsyncSession) -> None:
    """Add username / password_hash columns if missing (safe for existing DBs)."""
    for stmt in (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
    ):
        await session.execute(text(stmt))
    await session.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username
              ON users (username)
              WHERE username IS NOT NULL
            """
        )
    )
    await session.commit()


async def ensure_seed_users(session: AsyncSession) -> None:
    """Upsert Admin / VishalBhor / ShwetaPawar with hashed ADMIN_PASSWORD."""
    password = settings.ADMIN_PASSWORD or "Planeteye@2026"
    password_hash = hash_password(password)

    admin_role = await session.scalar(select(Role).where(Role.role_code == "ADMIN"))
    if admin_role is None:
        for code, name, desc in [
            ("ADMIN", "Administrator", "Full system access"),
            ("OPS_ENGINEER", "Operations Engineer", "Monitoring and alarms"),
            ("MAINT_ENGINEER", "Maintenance Engineer", "Work orders and maintenance"),
            ("ASSET_ENGINEER", "Asset Engineer", "Asset registry and health"),
            ("FIELD_TECH", "Field Technician", "Inspections and field work"),
            ("EXECUTIVE", "Executive Management", "Dashboards and reports"),
            ("AUDITOR", "Auditor", "Read-only audit access"),
        ]:
            existing = await session.scalar(select(Role).where(Role.role_code == code))
            if not existing:
                session.add(Role(role_code=code, role_name=name, description=desc))
        await session.flush()
        admin_role = await session.scalar(select(Role).where(Role.role_code == "ADMIN"))

    for spec in SEED_USERS:
        user = await session.scalar(
            select(User).where(
                or_(User.username == spec["username"], User.email == spec["email"])
            )
        )
        if user is None:
            user = User(
                email=spec["email"],
                username=spec["username"],
                display_name=spec["display_name"],
                department=spec["department"],
                password_hash=password_hash,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            logger.info("Created user %s in users table", spec["username"])
        else:
            user.username = spec["username"]
            user.display_name = spec["display_name"]
            user.department = spec["department"]
            user.password_hash = password_hash
            user.is_active = True
            logger.info("Updated user %s in users table", spec["username"])

        if admin_role:
            link = await session.scalar(
                select(UserRole).where(
                    UserRole.user_id == user.user_id, UserRole.role_id == admin_role.role_id
                )
            )
            if link is None:
                session.add(UserRole(user_id=user.user_id, role_id=admin_role.role_id))

    await session.commit()


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> tuple[User, str] | None:
    """Return (user, role_code) if credentials match an active DB user."""
    ident = username.strip()
    if not ident or not password:
        return None

    user = await session.scalar(
        select(User).where(
            or_(User.username == ident, User.email == ident, User.display_name == ident),
            User.is_active.is_(True),
        )
    )
    if user is None or not verify_password(password, user.password_hash):
        return None

    role_code = "ADMIN"
    role_row = await session.scalar(
        select(Role.role_code)
        .join(UserRole, UserRole.role_id == Role.role_id)
        .where(UserRole.user_id == user.user_id)
        .limit(1)
    )
    if role_row:
        role_code = str(role_row)
    return user, role_code


def user_public_dict(user: User, role: str) -> dict[str, Any]:
    return {
        "user_id": str(user.user_id),
        "username": user.username or user.display_name,
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "role": role,
        "is_active": user.is_active,
    }
