from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    validate_password,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.plaintext_security import require_frontend_secure_transport
from app.rate_limit import enforce_auth_rate_limit, enforce_frontend_route_rate_limit
from app.schemas import TokenResponse, UserLogin, UserRegister
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api",
    tags=["auth"],
    dependencies=[Depends(require_frontend_secure_transport)],
)


@router.post("/signup")
def register(user: UserRegister, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(request, action="signup", account_identifier=user.email)
    validate_password(user.password)

    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
def login(user: UserLogin, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(request, action="login", account_identifier=user.email)
    existing_user = db.query(User).filter(User.email == user.email).first()

    if not existing_user or not verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": existing_user.email})

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    enforce_frontend_route_rate_limit(route="me", user_email=current_user["email"])
    return {"email": current_user["email"]}
