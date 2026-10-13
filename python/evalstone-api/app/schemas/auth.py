import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    created_at: datetime


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt input limit
    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class AuthOut(BaseModel):
    user: UserOut
    token: str
