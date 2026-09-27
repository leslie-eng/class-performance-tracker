from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.config import get_settings
from app.deps import DB, CurrentUser
from app.models import User
from app.schemas import RegisterIn, Token, UserOut, UserUpdate
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, db: DB):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        name=body.name,
        email=email,
        phone_number=body.phone_number,
        whatsapp_opt_in=body.whatsapp_opt_in and body.phone_number is not None,
        password_hash=hash_password(body.password),
        is_admin=email in get_settings().admin_email_set,
    )
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """OAuth2 password flow: send the email as `username`."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: UserUpdate, user: CurrentUser, db: DB):
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    if user.phone_number is None:
        user.whatsapp_opt_in = False
    db.commit()
    return user
