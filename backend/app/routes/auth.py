"""Authentication routes — register, OTP, login, refresh (stateless JWT)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    ResendOtpRequest,
    UserPublic,
    VerifyOtpRequest,
)
from app.security.http_errors import GENERIC_EMAIL
from app.security.rate_limit import enforce_auth_rate_limit
from app.services.auth_service import AuthService
from app.services.email_service import EmailDeliveryError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _validation_status(exc: ValueError) -> int:
    detail = str(exc).lower()
    if "already" in detail or "taken" in detail:
        return status.HTTP_409_CONFLICT
    if "not verified" in detail:
        return status.HTTP_403_FORBIDDEN
    if "invalid credentials" in detail or "disabled" in detail:
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_400_BAD_REQUEST


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    enforce_auth_rate_limit(raw, action="register", identity=str(request.email))
    try:
        return await AuthService.register(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=_validation_status(exc), detail=str(exc)) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=GENERIC_EMAIL,
        ) from exc


@router.post("/verify-otp", response_model=AuthTokenResponse)
async def verify_otp(
    request: VerifyOtpRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="verify-otp", identity=request.email)
    try:
        return await AuthService.verify_otp(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=_validation_status(exc), detail=str(exc)) from exc


@router.post("/resend-otp", response_model=RegisterResponse)
async def resend_otp(
    request: ResendOtpRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    enforce_auth_rate_limit(raw, action="resend-otp", identity=request.email)
    try:
        return await AuthService.resend_otp(db, request.email)
    except ValueError as exc:
        raise HTTPException(status_code=_validation_status(exc), detail=str(exc)) from exc
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=GENERIC_EMAIL,
        ) from exc


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    request: LoginRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="login", identity=request.identifier)
    try:
        return await AuthService.login(db, request)
    except ValueError as exc:
        raise HTTPException(status_code=_validation_status(exc), detail=str(exc)) from exc


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(
    request: RefreshRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="refresh")
    try:
        return await AuthService.refresh(db, request.refresh_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: User = Depends(get_current_user)) -> MessageResponse:
    # Stateless JWT — client must discard access + refresh tokens.
    _ = current_user
    return MessageResponse(status="ok", message="Logged out")
