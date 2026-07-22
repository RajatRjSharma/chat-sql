"""Auth API + password security tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import SecretStr
import pytest

from app.models.email_otp import EmailOtp
from app.models.user import User
from app.schemas.auth import AuthTokenResponse, RegisterRequest, RegisterResponse, UserPublic
from app.security.password_policy import validate_password_strength
from app.security.passwords import hash_password, verify_password
from tests.conftest import DEMO_USER_ID

STRONG_PASSWORD = "Str0ng!Pass99"


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
        token = AuthTokenResponse(
            access_token="test.jwt.token",
            refresh_token="test.refresh.token",
            expires_in=1800,
            user=UserPublic.model_validate(sample_user),
        )
        with patch(
            "app.routes.auth.AuthService.login",
            new=AsyncMock(return_value=token),
        ):
            response = unauthenticated_client.post(
                "/api/auth/login",
                json={"identifier": "analyst", "password": STRONG_PASSWORD},
            )
        assert response.status_code == 200
        body = response.json()
        assert body["access_token"] == "test.jwt.token"
        assert body["refresh_token"] == "test.refresh.token"
        assert body["expires_in"] == 1800
        assert "password" not in body
        assert body["user"]["username"] == "analyst"

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
                return_value=("jwt-refresh", 604800),
            ),
        ):
            response = await AuthService.verify_otp(
                mock_db_session,
                VerifyOtpRequest(email=sample_user.email, code=code),
            )

        assert sample_user.email_verified is True
        assert otp.consumed_at is not None
        assert response.access_token == "jwt-access"
        assert response.refresh_token == "jwt-refresh"
        assert response.expires_in == 1800
