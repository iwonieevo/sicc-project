import os
import secrets
import string
from datetime import datetime, timedelta, timezone

import jwt
from app.database import get_db
from app.models import User
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from email_validator import EmailNotValidError, validate_email
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWTError
from sqlalchemy.orm import Session

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30))
TOKEN_ISSUER = os.getenv("JWT_ISSUER", "sicc-backend")
TOKEN_TYPE = "access"

PASSWORD_HASHER = PasswordHasher(
    time_cost=int(os.getenv("ARGON2_TIME_COST", "3")),
    memory_cost=int(os.getenv("ARGON2_MEMORY_COST", "65536")),
    parallelism=int(os.getenv("ARGON2_PARALLELISM", "2")),
    hash_len=int(os.getenv("ARGON2_HASH_LEN", "32")),
    salt_len=int(os.getenv("ARGON2_SALT_LEN", "16")),
    type=Type.ID,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def _validate_jwt_settings() -> None:
    if ALGORITHM not in {"HS256", "HS384", "HS512"}:
        raise RuntimeError(f"Unsupported JWT_ALGORITHM: {ALGORITHM}")

    if SECRET_KEY is None or len(SECRET_KEY) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be changed to a high-entropy secret")


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password.startswith("$argon2id$"):
        return False

    try:
        return PASSWORD_HASHER.verify(hashed_password, plain_password)
    except (InvalidHashError, VerifyMismatchError, VerificationError):
        return False


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must have at least 8 characters"
        )

    if password != password.strip():
        raise HTTPException(
            status_code=400, detail="Password cannot start or end with spaces"
        )

    if not any(char.isdigit() for char in password):
        raise HTTPException(
            status_code=400, detail="Password must contain at least one number"
        )

    if not any(char.isupper() for char in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter",
        )
    if not any(char in string.punctuation for char in password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one special character",
        )


def create_access_token(data: dict) -> str:
    _validate_jwt_settings()
    subject = data.get("sub")
    if not isinstance(subject, str) or not subject:
        raise RuntimeError("Access tokens require a non-empty subject")

    issued_at = datetime.now(timezone.utc)
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    token_id = secrets.token_urlsafe(16)
    to_encode = {
        "sub": subject,
        "typ": TOKEN_TYPE,
        "iss": TOKEN_ISSUER,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": expire,
        "jti": token_id,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    optional: bool = False,
    db: Session = Depends(get_db),
):
    """Get current user from JWT token."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        if optional:
            return None
        raise credentials_exception

    try:
        _validate_jwt_settings()
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            issuer=TOKEN_ISSUER,
            options={
                "require": ["exp", "iat", "nbf", "jti", "iss", "sub"],
                "verify_aud": False,
            },
        )
        if payload.get("typ") != TOKEN_TYPE:
            if optional:
                return None
            raise credentials_exception

        email = payload.get("sub")

        if not isinstance(email, str):
            if optional:
                return None
            raise credentials_exception
        try:
            email = validate_email(email, check_deliverability=False).normalized
        except EmailNotValidError:
            if optional:
                return None
            raise credentials_exception

    except (ExpiredSignatureError, InvalidTokenError, PyJWTError, RuntimeError):
        if optional:
            return None
        raise credentials_exception

    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()

    if user is None:
        if optional:
            return None
        raise credentials_exception

    return {"email": user.email}
