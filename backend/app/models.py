from sqlalchemy import Column, BigInteger, Text, DateTime, Boolean
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True)
    email = Column(Text, unique=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, default=False)
