"""Auth request/response bodies."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class UserOut(ORMModel):
    id: str
    org_id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None = None


class SessionOut(BaseModel):
    user: UserOut
    organization_name: str
    tokens: TokenPair


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=10, max_length=200)
    role: str = "supervisor"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=200)


# ---- mobile device pairing ----


class PairingCodeOut(BaseModel):
    code: str
    agent_id: str
    expires_at: datetime


class PairDeviceRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    platform: str = "android"
    device_name: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    push_token: str | None = None


class DeviceSessionOut(BaseModel):
    device_token: str
    device_id: str
    agent_id: str
    agent_name: str
    agent_number: str
    org_id: str
    organization_name: str
