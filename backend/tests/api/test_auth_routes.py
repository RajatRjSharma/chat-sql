"""Auth API + password security tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.models.email_otp import EmailOtp
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import AuthTokenResponse, RegisterRequest, RegisterResponse, UserPublic
from app.security.password_policy import validate_password_strength
from app.security.passwords import hash_password, verify_password
from app.services.auth_service import IssuedAuth
from tests.conftest import DEMO_USER_ID

STRONG_PASSWORD = "Str0ng!Pass99"


def _issued_auth(sample_user: User, *, expires_in: int = 1800) -> IssuedAuth:
    return IssuedAuth(
        access_token="test.jwt.token",
        refresh_token="test.refresh.token",
        refresh_max_age=604800,
        response=AuthTokenResponse(
            expires_in=expires_in,
            user=UserPublic.model_validate(sample_user),
        ),
    )


def _active_refresh_row(user: User) -> MagicMock:
    row = MagicMock(spec=RefreshToken)
    row.user_id = user.id
    row.revoked_at = None
    row.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    row.revoke_reason = None
    return row


class TestAuthRegister:
    def test_register_sends_otp(self, unauthenticated_client: TestClient) -> None:
        with patch(
            "app.routes.auth.AuthService.register",
            new=AsyncMock(return_value=RegisterResponse(email="new@example.com")),
        ):
            response = unauthenticated_client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "username": "newuser",
                    "password": STRONG_PASSWORD,
                    "password_confirm": STRONG_PASSWORD,
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "otp_sent"
        assert body["email"] == "new@example.com"

    def test_register_verified_when_otp_disabled(
        self, unauthenticated_client: TestClient
    ) -> None:
        with patch(
            "app.routes.auth.AuthService.register",
            new=AsyncMock(
                return_value=RegisterResponse(
                    status="verified",
                    email="new@example.com",
                    message="Account created. You can log in.",
                )
            ),
        ):
            response = unauthenticated_client.post(
                "/api/auth/register",
                json={
                    "email": "new@example.com",
                    "username": "newuser",
                    "password": STRONG_PASSWORD,
                    "password_confirm": STRONG_PASSWORD,
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "verified"
        assert body["message"] == "Account created. You can log in."

    def test_register_requires_confirm_match(self, unauthenticated_client: TestClient) -> None:
        response = unauthenticated_client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "username": "newuser",
                "password": STRONG_PASSWORD,
                "password_confirm": "Different!Pass1",
            },
        )
        assert response.status_code == 422

    def test_register_rejects_weak_password(self, unauthenticated_client: TestClient) -> None:
        response = unauthenticated_client.post(
            "/api/auth/register",
            json={
                "email": "new@example.com",
                "username": "newuser",
                "password": "password123",
                "password_confirm": "password123",
            },
        )
        assert response.status_code == 422

    def test_register_conflict(self, unauthenticated_client: TestClient) -> None:
        with patch(
            "app.routes.auth.AuthService.register",
            new=AsyncMock(side_effect=ValueError("Email is already registered")),
        ):
            response = unauthenticated_client.post(
                "/api/auth/register",
                json={
                    "email": "taken@example.com",
                    "username": "taken",
                    "password": STRONG_PASSWORD,
                    "password_confirm": STRONG_PASSWORD,
                },
            )
        assert response.status_code == 409


class TestAuthLogin:
    def test_login_success(self, unauthenticated_client: TestClient, sample_user: User) -> None:
        with patch(
            "app.routes.auth.AuthService.login",
            new=AsyncMock(return_value=_issued_auth(sample_user)),
        ):
            response = unauthenticated_client.post(
                "/api/auth/login",
                json={"identifier": "analyst", "password": STRONG_PASSWORD},
            )
        assert response.status_code == 200
        body = response.json()
        assert "access_token" not in body
        assert "refresh_token" not in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 1800
        assert "password" not in body
        assert body["user"]["username"] == "analyst"
        assert response.cookies.get("vdda_access") == "test.jwt.token"
        assert response.cookies.get("vdda_refresh") == "test.refresh.token"

    def test_login_unverified(self, unauthenticated_client: TestClient) -> None:
        with patch(
            "app.routes.auth.AuthService.login",
            new=AsyncMock(
                side_effect=ValueError(
                    "Email not verified. Check your inbox for the OTP code."
                )
            ),
        ):
            response = unauthenticated_client.post(
                "/api/auth/login",
                json={"identifier": "analyst", "password": STRONG_PASSWORD},
            )
        assert response.status_code == 403


class TestAuthMe:
    def test_me_requires_auth(self, unauthenticated_client: TestClient) -> None:
        response = unauthenticated_client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_returns_user(self, client: TestClient, sample_user: User) -> None:
        response = client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["id"] == str(sample_user.id)
        assert response.json()["email"] == sample_user.email


class TestAuthLogout:
    def test_logout_clears_session(self, client: TestClient) -> None:
        with patch(
            "app.routes.auth.AuthService.logout",
            new=AsyncMock(return_value=None),
        ) as logout:
            response = client.post("/api/auth/logout")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": "Logged out"}
        logout.assert_awaited_once()
        set_cookie = ",".join(response.headers.get_list("set-cookie"))
        assert "vdda_access" in set_cookie
        assert "vdda_refresh" in set_cookie

    async def test_logout_revokes_refresh_row(
        self, mock_db_session, sample_user: User
    ) -> None:
        from app.services.auth_service import AuthService

        row = _active_refresh_row(sample_user)
        with (
            patch(
                "app.services.auth_service.decode_token",
                return_value={"sub": str(sample_user.id), "jti": "logout-jti"},
            ),
            patch.object(
                AuthService,
                "_get_refresh_row",
                new=AsyncMock(return_value=row),
            ),
        ):
            await AuthService.logout(
                mock_db_session,
                user_id=sample_user.id,
                refresh_token="refresh-token-value",
                revoke_all=True,
            )

        assert row.revoked_at is not None
        assert row.revoke_reason == "logout"
        mock_db_session.execute.assert_awaited()
        mock_db_session.flush.assert_awaited()


class TestAuthProtectsData:
    def test_connect_requires_auth(self, unauthenticated_client: TestClient) -> None:
        response = unauthenticated_client.post(
            "/api/data/connect",
            json={
                "name": "x",
                "host": "localhost",
                "port": 5433,
                "database": "bi_warehouse",
                "username": "u",
                "password": "p",
            },
        )
        assert response.status_code == 401


class TestPasswordHelpers:
    def test_hash_and_verify_roundtrip(self) -> None:
        hashed = hash_password(STRONG_PASSWORD)
        assert hashed != STRONG_PASSWORD
        assert verify_password(STRONG_PASSWORD, hashed) is True
        assert verify_password("wrong", hashed) is False

    def test_secret_str_not_in_repr(self) -> None:
        req = RegisterRequest(
            email="a@example.com",
            username="alice",
            password=SecretStr(STRONG_PASSWORD),
            password_confirm=SecretStr(STRONG_PASSWORD),
        )
        rendered = repr(req)
        assert STRONG_PASSWORD not in rendered
        assert "**********" in rendered or "SecretStr" in rendered

    def test_password_policy_rejects_username_substring(self) -> None:
        with pytest.raises(ValueError, match="username or email"):
            validate_password_strength("AliceUser!99xx", username="aliceuser", email="a@x.com")


class TestAuthServiceOtp:
    async def test_verify_otp_marks_verified(self, mock_db_session, sample_user: User) -> None:
        from app.schemas.auth import VerifyOtpRequest
        from app.services.auth_service import AuthService

        sample_user.email_verified = False
        code = "123456"
        otp = EmailOtp(
            id=DEMO_USER_ID,
            user_id=sample_user.id,
            purpose="verify_email",
            code_hash=hash_password(code),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            consumed_at=None,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = sample_user
        otp_result = MagicMock()
        otp_result.scalar_one_or_none.return_value = otp
        mock_db_session.execute = AsyncMock(side_effect=[user_result, otp_result])

        with (
            patch(
                "app.services.auth_service.create_access_token",
                return_value=("jwt-access", 1800),
            ),
            patch(
                "app.services.auth_service.create_refresh_token",
                return_value=("jwt-refresh", 604800, "refresh-jti"),
            ),
        ):
            issued = await AuthService.verify_otp(
                mock_db_session,
                VerifyOtpRequest(email=sample_user.email, code=code),
            )

        assert sample_user.email_verified is True
        assert otp.consumed_at is not None
        assert issued.access_token == "jwt-access"
        assert issued.refresh_token == "jwt-refresh"
        assert issued.refresh_max_age == 604800
        assert issued.response.expires_in == 1800
        assert issued.response.user.email == sample_user.email
        assert "access_token" not in issued.response.model_dump()
        added = mock_db_session.add.call_args[0][0]
        assert isinstance(added, RefreshToken)
        assert added.user_id == sample_user.id

    async def test_register_skips_otp_when_disabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        from app.services.auth_service import AuthService

        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=empty)
        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock()

        request = RegisterRequest(
            email="fresh@example.com",
            username="freshuser",
            password=SecretStr(STRONG_PASSWORD),
            password_confirm=SecretStr(STRONG_PASSWORD),
        )

        with (
            patch("app.services.auth_service.settings") as mock_settings,
            patch("app.services.auth_service.hash_password", return_value="hashed"),
            patch(
                "app.services.auth_service.AuthService._issue_and_send_otp",
                new=AsyncMock(),
            ) as send_otp,
        ):
            mock_settings.email_otp_enabled = False
            response = await AuthService.register(mock_db_session, request)

        assert response.status == "verified"
        assert response.email == "fresh@example.com"
        assert response.message == "Account created. You can log in."
        send_otp.assert_not_awaited()
        added_user = mock_db_session.add.call_args[0][0]
        assert added_user.email_verified is True

    async def test_resend_otp_rejects_when_disabled(self, mock_db_session) -> None:
        from app.services.auth_service import AuthService

        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.email_otp_enabled = False
            with pytest.raises(ValueError, match="currently disabled"):
                await AuthService.resend_otp(mock_db_session, "a@example.com")

    async def test_login_allows_unverified_when_otp_disabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import AuthService

        sample_user.email_verified = False
        sample_user.password_hash = hash_password(STRONG_PASSWORD)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = sample_user
        mock_db_session.execute = AsyncMock(return_value=user_result)

        with (
            patch("app.services.auth_service.settings") as mock_settings,
            patch(
                "app.services.auth_service.create_access_token",
                return_value=("jwt-access", 1800),
            ),
            patch(
                "app.services.auth_service.create_refresh_token",
                return_value=("jwt-refresh", 604800, "refresh-jti"),
            ),
        ):
            mock_settings.email_otp_enabled = False
            issued = await AuthService.login(
                mock_db_session,
                LoginRequest(identifier=sample_user.email, password=SecretStr(STRONG_PASSWORD)),
            )

        assert issued.access_token == "jwt-access"
        assert issued.response.expires_in == 1800
        assert issued.response.user.id == sample_user.id
        added = mock_db_session.add.call_args[0][0]
        assert isinstance(added, RefreshToken)

    async def test_login_still_blocks_unverified_when_otp_enabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        """Flipping the flag back on must restore the verification gate."""
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import AuthService

        sample_user.email_verified = False
        sample_user.password_hash = hash_password(STRONG_PASSWORD)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = sample_user
        mock_db_session.execute = AsyncMock(return_value=user_result)

        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.email_otp_enabled = True
            with pytest.raises(ValueError, match="not verified"):
                await AuthService.login(
                    mock_db_session,
                    LoginRequest(
                        identifier=sample_user.email,
                        password=SecretStr(STRONG_PASSWORD),
                    ),
                )

    async def test_login_still_blocks_disabled_account_when_otp_disabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        """Disabling OTP must not weaken any other login check."""
        from app.schemas.auth import LoginRequest
        from app.services.auth_service import AuthService

        sample_user.is_active = False
        sample_user.password_hash = hash_password(STRONG_PASSWORD)
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = sample_user
        mock_db_session.execute = AsyncMock(return_value=user_result)

        with patch("app.services.auth_service.settings") as mock_settings:
            mock_settings.email_otp_enabled = False
            with pytest.raises(ValueError, match="disabled"):
                await AuthService.login(
                    mock_db_session,
                    LoginRequest(
                        identifier=sample_user.email,
                        password=SecretStr(STRONG_PASSWORD),
                    ),
                )

    async def test_refresh_allows_unverified_when_otp_disabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        from app.services.auth_service import AuthService

        sample_user.email_verified = False
        mock_db_session.get = AsyncMock(return_value=sample_user)
        row = _active_refresh_row(sample_user)

        with (
            patch("app.services.auth_service.settings") as mock_settings,
            patch(
                "app.services.auth_service.decode_token",
                return_value={"sub": str(sample_user.id), "jti": "old-jti"},
            ),
            patch.object(
                AuthService,
                "_get_refresh_row",
                new=AsyncMock(return_value=row),
            ),
            patch(
                "app.services.auth_service.create_access_token",
                return_value=("jwt-access", 1800),
            ),
            patch(
                "app.services.auth_service.create_refresh_token",
                return_value=("jwt-refresh", 604800, "new-jti"),
            ),
        ):
            mock_settings.email_otp_enabled = False
            issued = await AuthService.refresh(mock_db_session, "refresh-token-value")

        assert issued.access_token == "jwt-access"
        assert issued.response.expires_in == 1800
        assert row.revoked_at is not None
        assert row.revoke_reason == "rotated"
        added = mock_db_session.add.call_args[0][0]
        assert isinstance(added, RefreshToken)

    async def test_refresh_blocks_unverified_when_otp_enabled(
        self, mock_db_session, sample_user: User
    ) -> None:
        from app.services.auth_service import AuthService

        sample_user.email_verified = False
        mock_db_session.get = AsyncMock(return_value=sample_user)
        row = _active_refresh_row(sample_user)

        with (
            patch("app.services.auth_service.settings") as mock_settings,
            patch(
                "app.services.auth_service.decode_token",
                return_value={"sub": str(sample_user.id), "jti": "old-jti"},
            ),
            patch.object(
                AuthService,
                "_get_refresh_row",
                new=AsyncMock(return_value=row),
            ),
        ):
            mock_settings.email_otp_enabled = True
            with pytest.raises(ValueError, match="not verified"):
                await AuthService.refresh(mock_db_session, "refresh-token-value")

    async def test_register_sends_otp_when_enabled(self, mock_db_session) -> None:
        """Default path is unchanged: a code is issued and emailed."""
        from app.services.auth_service import AuthService

        empty = MagicMock()
        empty.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=empty)
        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock()

        request = RegisterRequest(
            email="fresh@example.com",
            username="freshuser",
            password=SecretStr(STRONG_PASSWORD),
            password_confirm=SecretStr(STRONG_PASSWORD),
        )

        with (
            patch("app.services.auth_service.settings") as mock_settings,
            patch("app.services.auth_service.hash_password", return_value="hashed"),
            patch(
                "app.services.auth_service.AuthService._issue_and_send_otp",
                new=AsyncMock(),
            ) as send_otp,
        ):
            mock_settings.email_otp_enabled = True
            response = await AuthService.register(mock_db_session, request)

        assert response.status == "otp_sent"
        send_otp.assert_awaited_once()
        added_user = mock_db_session.add.call_args[0][0]
        assert added_user.email_verified is False
