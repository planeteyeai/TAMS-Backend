"""Auth API — login against PostgreSQL users table."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_session
from app.db.init_db import is_db_ready
from app.models.entities import User
from app.schemas.response import ApiResponse, ResponseMeta
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    user_public_dict,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=200)
    password: str = Field(..., min_length=1, max_length=200)


@router.post("/login", response_model=ApiResponse)
async def login(
    payload: LoginRequest,
    session: Optional[AsyncSession] = Depends(get_session),
):
    if not is_db_ready() or session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable — cannot authenticate against users table",
        )

    result = await authenticate_user(session, payload.username, payload.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    user, role = result
    token = create_access_token(
        subject=user.username or user.display_name,
        role=role,
        user_id=str(user.user_id),
    )
    return ApiResponse(
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": user_public_dict(user, role),
        },
        meta=ResponseMeta(),
    )


@router.get("/users", response_model=ApiResponse)
async def list_users(session: Optional[AsyncSession] = Depends(get_session)):
    """List active users (no password hashes)."""
    if not is_db_ready() or session is None:
        raise HTTPException(status_code=503, detail="Database unavailable")
    rows = (
        await session.scalars(select(User).where(User.is_active.is_(True)).order_by(User.username))
    ).all()
    return ApiResponse(
        data=[
            {
                "user_id": str(u.user_id),
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "department": u.department,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in rows
        ],
        meta=ResponseMeta(),
    )
