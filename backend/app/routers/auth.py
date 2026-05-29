from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    validate_password,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas import TokenResponse, UserLogin, UserRegister
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/signup")
def register(user: UserRegister, db: Session = Depends(get_db)):
    validate_password(user.password)

    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = hash_password(user.password)
    new_user = User(email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"status": "User registered successfully"}


@router.post("/login", response_model=TokenResponse)
def login(user: UserLogin, db: Session = Depends(get_db)):
    existing_user = (
        db.query(User)
        .filter(User.email == user.email)
        .first()
    )

    if not existing_user or not verify_password(user.password, existing_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(data={"sub": existing_user.email})

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    return {"email": current_user["email"]}
