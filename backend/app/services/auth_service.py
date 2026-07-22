"""Authentication and email-OTP orchestration (stateless JWT)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_otp import EmailOtp
from app.models.user import User
from app.schemas.auth import (
    AuthTokenResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    UserPublic,
    VerifyOtpRequest,
)
from app.security.jwt import create_access_token, create_refresh_token, decode_token
from app.security.passwords import (
    hash_password,
    verify_password,
    verify_password_or_dummy,
)
from app.services.email_service import EmailService


class AuthService:
    """Register → OTP verify → login / refresh (no server sessions)."""

    @staticmethod
    async def register(session: AsyncSession, request: RegisterRequest) -> RegisterResponse:
        existing = await session.execute(
            select(User).where(
                or_(User.email == request.email, User.username == request.username)
            )
        )
        conflict = existing.scalar_one_or_none()
        if conflict is not None:
            if conflict.email == request.email:
                raise ValueError("Email is already registered")
            raise ValueError("Username is already taken")

        plain = request.password.get_secret_value()
        user = User(
            email=request.email,
            username=request.username,
            password_hash=hash_password(plain),
            role="analyst",
            is_active=True,
            email_verified=False,
        )
        session.add(user)
        await session.flush()

        await AuthService._issue_and_send_otp(session, user)
        return RegisterResponse(email=user.email)

    @staticmethod
    async def resend_otp(session: AsyncSession, email: str) -> RegisterResponse:
        user = await AuthService._get_user_by_email(session, email)
        if user.email_verified:
            raise ValueError("Email is already verified. You can log in.")
        await AuthService._issue_and_send_otp(session, user)
        return RegisterResponse(email=user.email, message="A new verification code was sent.")

    @staticmethod
    async def verify_otp(session: AsyncSession, request: VerifyOtpRequest) -> AuthTokenResponse:
        user = await AuthService._get_user_by_email(session, request.email)
        if user.email_verified:
            return AuthService._token_response(user)

        result = await session.execute(
            select(EmailOtp)
            .where(EmailOtp.user_id == user.id)
            .where(EmailOtp.purpose == "verify_email")
            .where(EmailOtp.consumed_at.is_(None))
            .order_by(EmailOtp.created_at.desc())
            .limit(1)
        )
        otp = result.scalar_one_or_none()
        now = datetime.now(timezone.utc)
        if otp is None or otp.expires_at < now:
            raise ValueError("Verification code expired. Request a new one.")
        if not verify_password(request.code, otp.code_hash):
            raise ValueError("Invalid verification code")

        otp.consumed_at = now
        user.email_verified = True
        await session.flush()
        return AuthService._token_response(user)

    @staticmethod
    async def login(session: AsyncSession, request: LoginRequest) -> AuthTokenResponse:
        result = await session.execute(
            select(User).where(
                or_(User.email == request.identifier, User.username == request.identifier)
            )
        )
        user = result.scalar_one_or_none()
        plain = request.password.get_secret_value()
        hashed = user.password_hash if user is not None else None
        if not verify_password_or_dummy(plain, hashed) or user is None:
            raise ValueError("Invalid credentials")
        if not user.is_active:
            raise ValueError("Account is disabled")
        if not user.email_verified:
            raise ValueError("Email not verified. Check your inbox for the OTP code.")
        return AuthService._token_response(user)

    @staticmethod
    async def refresh(session: AsyncSession, refresh_token: str) -> AuthTokenResponse:
        payload = decode_token(refresh_token, expected_type="refresh")
        user_id = UUID(str(payload["sub"]))
        user = await AuthService.get_user(session, user_id)
        if not user.email_verified:
            raise ValueError("Email not verified")
        return AuthService._token_response(user)

    @staticmethod
    async def get_user(session: AsyncSession, user_id: UUID) -> User:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise ValueError("User not found")
        return user

    @staticmethod
    def _token_response(user: User) -> AuthTokenResponse:
        access, expires_in = create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
        )
        refresh, _ = create_refresh_token(user_id=user.id)
        return AuthTokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=expires_in,
            user=UserPublic.model_validate(user),
        )

    @staticmethod
    async def _get_user_by_email(session: AsyncSession, email: str) -> User:
        result = await session.execute(select(User).where(User.email == email.lower()))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError("No account found for that email")
        return user

    @staticmethod
    async def _issue_and_send_otp(session: AsyncSession, user: User) -> None:
        await session.execute(
            update(EmailOtp)
            .where(EmailOtp.user_id == user.id)
            .where(EmailOtp.purpose == "verify_email")
            .where(EmailOtp.consumed_at.is_(None))
            .values(consumed_at=datetime.now(timezone.utc))
        )

        code = "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
        otp = EmailOtp(
            user_id=user.id,
            purpose="verify_email",
            code_hash=hash_password(code),
            expires_at=datetime.now(timezone.utc)
            + timedelta(minutes=settings.otp_expire_minutes),
        )
        session.add(otp)
        await session.flush()
        EmailService.send_otp(to_email=user.email, code=code, username=user.username)
