from fastapi import APIRouter, HTTPException, Depends
from app.schemas import UserRegister, UserLogin, TokenResponse, UserResponse
from app.auth import (
    users_db,
    hash_password,
    verify_password,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/api", tags=["auth"])

@router.post("/signup")
def register(user: UserRegister):
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="Email already registered")
    print("PASSWORD:", user.password)
    print("TYPE:", type(user.password))
    print("LENGTH:", len(user.password))
    hashed_password = hash_password(user.password)
    users_db[user.email] = {
        "email": user.email,
        "hashed_password": hashed_password
    }
    return "User registered successfully"

@router.post("/login", response_model=TokenResponse)
def login(user : UserLogin):
    existing_user = users_db.get(user.email)
    
    if not existing_user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(user.password, existing_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": existing_user["email"]})

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me")
def read_current_user(current_user: dict = Depends(get_current_user)):
    return{
        "email": current_user["email"]
    }