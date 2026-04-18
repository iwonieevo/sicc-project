from sqlalchemy import Column, Integer, BigInteger, Text, DateTime
from sqlalchemy.sql import func
from .database import Base


class Device(Base):
    __tablename__ = "devices"

    id = Column(BigInteger, primary_key=True)
    name = Column(Text, nullable=True)
    host = Column(Text, nullable=True)
    port = Column(Integer, nullable=True)
    status = Column(Text, default="offline")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommandLog(Base):
    __tablename__ = "command_logs"

    id = Column(BigInteger, primary_key=True)
    command_id = Column(Integer)
    device_id = Column(BigInteger)
    status = Column(Text)
    result = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
