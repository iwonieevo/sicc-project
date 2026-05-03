from fastapi import APIRouter, HTTPException, Depends
from app.schemas import UserRegister, UserLogin, TokenResponse
from app.auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)
from app.database import SessionLocal
from app.models import User

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/signup")
def register(user: UserRegister):
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == user.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = hash_password(user.password)
        new_user = User(email=user.email, hashed_password=hashed_password)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {"status": "User registered successfully"}
    finally:
        db.close()


@router.post("/login", response_model=TokenResponse)
def login(user: UserLogin):
    db = SessionLocal()
    try:
        existing_user = db.query(User).filter(User.email == user.email).first()

        if not existing_user:
            raise HTTPException(status_code=401, detail="Invalid email or password")

        if not verify_password(user.password, existing_user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        access_token = create_access_token(data={"sub": existing_user.email})

        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
    finally:
        db.close()


@router.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    return {"email": current_user["email"]}