from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


def validate_new_password(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long")
    if len(value.encode("utf-8")) > 72:  # bcrypt limit
        raise ValueError("Password is too long")
    return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str | None
    email: str
    role: str
    status: str | None
    locked: bool
    failed_login_attempts: int
    vendor_ids: list[int]
    all_vendors: bool  # True for Admin: can switch between every vendor


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class InviteRequest(BaseModel):
    full_name: str
    email: EmailStr
    role: Literal["Manager", "Staff"]
    vendor_ids: list[int]


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: Literal["Manager", "Staff"] | None = None
    vendor_ids: list[int] | None = None


class SetPasswordRequest(BaseModel):
    token: str
    password: str

    _check = field_validator("password")(validate_new_password)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    _check = field_validator("new_password")(validate_new_password)


class Message(BaseModel):
    message: str