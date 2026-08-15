"""Auth request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator, model_validator

from app.security.password_policy import validate_password_strength


class RegisterRequest(BaseModel):
    """Register payload. Passwords are SecretStr (hashed before storage)."""

    email: EmailStr
    username: str = Field(..., min_length=3, max_length=64)
    password: SecretStr = Field(..., min_length=12, max_length=72)
    password_confirm: SecretStr = Field(..., min_length=12, max_length=72)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.replace("_", "").isalnum():
            raise ValueError("Username may only contain letters, numbers, and underscores")
        return cleaned.lower()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @model_validator(mode="after")
    def confirm_and_strengthen(self) -> RegisterRequest:
        password = self.password.get_secret_value()
        confirm = self.password_confirm.get_secret_value()
        if password != confirm:
            raise ValueError("Passwords do not match")
        validate_password_strength(password, username=self.username, email=str(self.email))
        return self


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=8)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip()


class ResendOtpRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()


class LoginRequest(BaseModel):
    """Login with email or username + password."""

    identifier: str = Field(..., min_length=3, max_length=255, description="Email or username")
    password: SecretStr = Field(..., min_length=1, max_length=72)

    @field_validator("identifier")
    @classmethod
    def normalize_identifier(cls, value: str) -> str:
        return value.strip().lower()


class RefreshRequest(BaseModel):
    """Optional body fallback for API clients; browsers send the refresh cookie."""

    refresh_token: str | None = Field(default=None, min_length=20)


class UserPublic(BaseModel):
    id: UUID
    email: str
    username: str
    role: str
    email_verified: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AuthTokenResponse(BaseModel):
    """Login/refresh/OTP response. JWTs go in httpOnly cookies, not this body."""

    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    user: UserPublic


class RegisterResponse(BaseModel):
    status: Literal["otp_sent", "verified"] = "otp_sent"
    email: str
    message: str = "Verification code sent to your email."


class MessageResponse(BaseModel):
    status: str
    message: str


class AuthPublicConfig(BaseModel):
    """Unauthenticated feature flags for the auth UI."""

    registration_enabled: bool
    email_otp_enabled: bool
