from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.auth import AuthOut, LoginIn, RegisterIn, UserOut
from app.security import create_token
from app.services import users as user_service

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=AuthOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthOut:
    user = user_service.register(db, **body.model_dump())
    return AuthOut(user=UserOut.model_validate(user), token=create_token(user.id))


@router.post("/auth/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthOut:
    user = user_service.authenticate(db, email=body.email, password=body.password)
    return AuthOut(user=UserOut.model_validate(user), token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
