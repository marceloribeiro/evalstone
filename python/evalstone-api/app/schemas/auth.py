import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BCRYPT_MAX_BYTES = 72


def _within_bcrypt_limit(password: str) -> str:
    # bcrypt 5 raises on >72 BYTES; pydantic's max_length counts characters
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_BYTES} bytes")
    return password


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    created_at: datetime


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=BCRYPT_MAX_BYTES)
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)

    _bytes = field_validator("password")(_within_bcrypt_limit)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=BCRYPT_MAX_BYTES)

    _bytes = field_validator("password")(_within_bcrypt_limit)


class AuthOut(BaseModel):
    user: UserOut
    token: str
