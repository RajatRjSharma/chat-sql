"""Authentication orchestration — JWT cookies + revocable refresh sessions."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_otp import EmailOtp
from app.models.refresh_token import RefreshToken
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

_GENERIC_OTP = "Invalid or expired verification code"
_SOFT_OTP_SENT = "If an account needs verification, a code was sent."
_SOFT_REGISTERED = "If this email can be registered, next steps were sent."


def _hash_jti(jti: str) -> str:
    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class IssuedAuth:
    """Tokens for httpOnly cookies + public session payload for the JSON body."""

    access_token: str
    refresh_token: str
    refresh_max_age: int
    response: AuthTokenResponse


class AuthService:
    """Register → OTP verify → login / refresh with server-side refresh revoke."""

    @staticmethod
    async def register(session: AsyncSession, request: RegisterRequest) -> RegisterResponse:
        existing = await session.execute(
            select(User).where(
                or_(User.email == request.email, User.username == request.username)
            )
        )
        conflict = existing.scalar_one_or_none()
        otp_enabled = settings.email_otp_enabled

        # Same response if email/username already taken (don't leak which).
        if conflict is not None:
            if otp_enabled:
                return RegisterResponse(email=request.email, message=_SOFT_REGISTERED)
            return RegisterResponse(
                status="verified",
                email=request.email,
                message="Account created. You can log in.",
            )

        plain = request.password.get_secret_value()
        user = User(
            email=request.email,
            username=request.username,
            password_hash=hash_password(plain),
            role="analyst",
            is_active=True,
            email_verified=not otp_enabled,
        )
        session.add(user)
        await session.flush()

        if not otp_enabled:
            return RegisterResponse(
                status="verified",
                email=user.email,
                message="Account created. You can log in.",
            )

        await AuthService._issue_and_send_otp(session, user)
        return RegisterResponse(email=user.email, message=_SOFT_REGISTERED)

    @staticmethod
    async def resend_otp(session: AsyncSession, email: str) -> RegisterResponse:
        # Always 200-ish success; only send mail if there is an unverified user.
        if settings.email_otp_enabled:
            user = await AuthService._find_user_by_email(session, email)
            if user is not None and not user.email_verified:
                await AuthService._issue_and_send_otp(session, user)
        return RegisterResponse(email=email, message=_SOFT_OTP_SENT)

    @staticmethod
    async def verify_otp(
        session: AsyncSession,
        request: VerifyOtpRequest,
        *,
        user_agent: str | None = None,
    ) -> IssuedAuth:
        user = await AuthService._find_user_by_email(session, request.email)
        if user is None:
            raise ValueError(_GENERIC_OTP)
        if user.email_verified:
            return await AuthService.issue_session(session, user, user_agent=user_agent)

        result = await session.execute(
            select(EmailOtp)
            .where(EmailOtp.user_id == user.id)
            .where(EmailOtp.purpose == "verify_email")
            .where(EmailOtp.consumed_at.is_(None))
            .order_by(EmailOtp.created_at.desc())
            .limit(1)
        )
        otp = result.scalar_one_or_none()
        now = datetime.now(UTC)
        if otp is None or otp.expires_at < now:
            raise ValueError(_GENERIC_OTP)
        if otp.attempt_count >= settings.otp_max_attempts:
            otp.consumed_at = now
            await session.flush()
            raise ValueError(_GENERIC_OTP)
        if not verify_password(request.code, otp.code_hash):
            otp.attempt_count += 1
            if otp.attempt_count >= settings.otp_max_attempts:
                otp.consumed_at = now
            await session.flush()
            raise ValueError(_GENERIC_OTP)

        otp.consumed_at = now
        user.email_verified = True
        await session.flush()
        return await AuthService.issue_session(session, user, user_agent=user_agent)

    @staticmethod
    async def login(
        session: AsyncSession,
        request: LoginRequest,
        *,
        user_agent: str | None = None,
    ) -> IssuedAuth:
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
        if settings.email_otp_enabled and not user.email_verified:
            raise ValueError("Email not verified. Check your inbox for the OTP code.")
        return await AuthService.issue_session(session, user, user_agent=user_agent)

    @staticmethod
    async def refresh(
        session: AsyncSession,
        refresh_token: str,
        *,
        user_agent: str | None = None,
    ) -> IssuedAuth:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = str(payload.get("jti") or "")
        if not jti:
            raise ValueError("Invalid or expired token")

        row = await AuthService._get_refresh_row(session, jti)
        now = datetime.now(UTC)
        if row is None or row.revoked_at is not None or row.expires_at < now:
            raise ValueError("Invalid or expired token")

        user_id = UUID(str(payload["sub"]))
        if row.user_id != user_id:
            raise ValueError("Invalid or expired token")

        user = await AuthService.get_user(session, user_id)
        if settings.email_otp_enabled and not user.email_verified:
            raise ValueError("Email not verified")

        row.revoked_at = now
        row.revoke_reason = "rotated"
        await session.flush()
        return await AuthService.issue_session(session, user, user_agent=user_agent)

    @staticmethod
    async def logout(
        session: AsyncSession,
        *,
        user_id: UUID,
        refresh_token: str | None,
        revoke_all: bool = True,
    ) -> None:
        """Revoke the current refresh cookie and (by default) all sessions for the user."""
        now = datetime.now(UTC)
        if refresh_token:
            try:
                payload = decode_token(refresh_token, expected_type="refresh")
                jti = str(payload.get("jti") or "")
                row = await AuthService._get_refresh_row(session, jti) if jti else None
                if row is not None and row.user_id == user_id and row.revoked_at is None:
                    row.revoked_at = now
                    row.revoke_reason = "logout"
            except ValueError:
                pass

        if revoke_all:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id)
                .where(RefreshToken.revoked_at.is_(None))
                .values(revoked_at=now, revoke_reason="logout_all")
            )
        await session.flush()

    @staticmethod
    async def get_user(session: AsyncSession, user_id: UUID) -> User:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            raise ValueError("User not found")
        return user

    @staticmethod
    async def issue_session(
        session: AsyncSession,
        user: User,
        *,
        user_agent: str | None = None,
    ) -> IssuedAuth:
        access, expires_in = create_access_token(
            user_id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
        )
        refresh, refresh_max_age, jti = create_refresh_token(user_id=user.id)
        row = RefreshToken(
            user_id=user.id,
            jti_hash=_hash_jti(jti),
            expires_at=datetime.now(UTC) + timedelta(seconds=refresh_max_age),
            user_agent=(user_agent or "")[:512] or None,
        )
        session.add(row)
        await session.flush()
        return IssuedAuth(
            access_token=access,
            refresh_token=refresh,
            refresh_max_age=refresh_max_age,
            response=AuthTokenResponse(
                expires_in=expires_in,
                user=UserPublic.model_validate(user),
            ),
        )

    @staticmethod
    async def _get_refresh_row(session: AsyncSession, jti: str) -> RefreshToken | None:
        result = await session.execute(
            select(RefreshToken).where(RefreshToken.jti_hash == _hash_jti(jti))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _find_user_by_email(session: AsyncSession, email: str) -> User | None:
        result = await session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    @staticmethod
    async def _issue_and_send_otp(session: AsyncSession, user: User) -> None:
        await session.execute(
            update(EmailOtp)
            .where(EmailOtp.user_id == user.id)
            .where(EmailOtp.purpose == "verify_email")
            .where(EmailOtp.consumed_at.is_(None))
            .values(consumed_at=datetime.now(UTC))
        )

        code = "".join(secrets.choice("0123456789") for _ in range(settings.otp_length))
        otp = EmailOtp(
            user_id=user.id,
            purpose="verify_email",
            code_hash=hash_password(code),
            expires_at=datetime.now(UTC)
            + timedelta(minutes=settings.otp_expire_minutes),
            attempt_count=0,
        )
        session.add(otp)
        await session.flush()
        EmailService.send_otp(to_email=user.email, code=code, username=user.username)
