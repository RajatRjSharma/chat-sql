"""Authentication routes — register, OTP, login, cookie refresh, logout revoke."""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps.auth import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AuthPublicConfig,
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
from app.security.auth_cookies import (
    clear_auth_cookies,
    refresh_cookie_name,
    set_auth_cookies,
)
from app.security.http_errors import GENERIC_EMAIL
from app.security.rate_limit import enforce_auth_rate_limit
from app.services.auth_service import AuthService, IssuedAuth
from app.services.email_service import EmailDeliveryError

router = APIRouter(prefix="/api/auth", tags=["auth"])

_REGISTRATION_DISABLED = "New account registration is currently disabled."


def _validation_status(exc: ValueError) -> int:
    detail = str(exc).lower()
    if "already" in detail or "taken" in detail:
        return status.HTTP_409_CONFLICT
    if "not verified" in detail:
        return status.HTTP_403_FORBIDDEN
    if "invalid credentials" in detail or "disabled" in detail:
        return status.HTTP_401_UNAUTHORIZED
    return status.HTTP_400_BAD_REQUEST


def _apply_session_cookies(response: Response, issued: IssuedAuth) -> AuthTokenResponse:
    set_auth_cookies(
        response,
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        access_max_age=issued.response.expires_in,
        refresh_max_age=issued.refresh_max_age,
    )
    return issued.response


def _user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


@router.get("/config", response_model=AuthPublicConfig)
async def auth_config() -> AuthPublicConfig:
    """Public flags for the login/register UI (no auth required)."""
    return AuthPublicConfig(
        registration_enabled=settings.registration_enabled,
        email_otp_enabled=settings.email_otp_enabled,
    )


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    raw: Request,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    if not settings.registration_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_REGISTRATION_DISABLED,
        )
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
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="verify-otp", identity=request.email)
    try:
        issued = await AuthService.verify_otp(
            db, request, user_agent=_user_agent(raw)
        )
        return _apply_session_cookies(response, issued)
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
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="login", identity=request.identifier)
    try:
        issued = await AuthService.login(db, request, user_agent=_user_agent(raw))
        return _apply_session_cookies(response, issued)
    except ValueError as exc:
        raise HTTPException(status_code=_validation_status(exc), detail=str(exc)) from exc


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(
    raw: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    body: RefreshRequest = Body(default_factory=RefreshRequest),
) -> AuthTokenResponse:
    enforce_auth_rate_limit(raw, action="refresh")
    token = raw.cookies.get(refresh_cookie_name()) or body.refresh_token
    if not token:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
        )
    try:
        issued = await AuthService.refresh(db, token, user_agent=_user_agent(raw))
        return _apply_session_cookies(response, issued)
    except ValueError as exc:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    raw: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    refresh_token = raw.cookies.get(refresh_cookie_name())
    await AuthService.logout(
        db,
        user_id=current_user.id,
        refresh_token=refresh_token,
        revoke_all=True,
    )
    clear_auth_cookies(response)
    return MessageResponse(status="ok", message="Logged out")
