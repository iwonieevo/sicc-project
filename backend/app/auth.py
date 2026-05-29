import os
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from app.database import get_db
from app.models import User
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your_secret_key_change_me_in_production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login", auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must have at least 8 characters")

    if len(password) > 72:
        raise HTTPException(status_code=400, detail="Password must have at most 72 characters")

    if password != password.strip():
        raise HTTPException(status_code=400, detail="Password cannot start or end with spaces")

    if not any(char.isdigit() for char in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one number")

    if not any(char.isupper() for char in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter")
    if not any(char in string.punctuation for char in password):
        raise HTTPException(status_code=400, detail="Password must contain at least one special character")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(
    token: str = Depends(oauth2_scheme), optional: bool = False, db: Session = Depends(get_db)
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
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")

        if email is None:
            if optional:
                return None
            raise credentials_exception

    except JWTError:
        if optional:
            return None
        raise credentials_exception

    user = db.query(User).filter(User.email == email, User.is_deleted == False).first()

    if user is None:
        if optional:
            return None
        raise credentials_exception

    return {"email": user.email}
