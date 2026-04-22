from sqlalchemy import Column, BigInteger, Text, DateTime, Boolean, ForeignKey, JSON
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


class Device(Base):
    __tablename__ = "devices"
    id = Column(BigInteger, primary_key=True)
    name = Column(Text, unique=True, nullable=False)
    status = Column(Text, nullable=False, default="offline")
    last_seen = Column(DateTime(timezone=True), nullable=True)
    registered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, default=False)


class Command(Base):
    __tablename__ = "commands"
    id = Column(BigInteger, primary_key=True)
    name = Column(Text, unique=True, nullable=False)
    description = Column(Text, nullable=True)
    python_code = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, default=False)


class CommandParameter(Base):
    __tablename__ = "command_parameters"
    id = Column(BigInteger, primary_key=True)
    command_id = Column(BigInteger, ForeignKey("commands.id"), nullable=False)
    name = Column(Text, nullable=False)
    param_type = Column(Text, nullable=False, default="text")
    is_required = Column(Boolean, nullable=False, default=True)
    default_value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, default=False)


class VCommandLog(Base):
    __tablename__ = "v_command_log"
    __table_args__ = {'info': {'is_view': True}}
    queue_id = Column(BigInteger, primary_key=True)
    device_id = Column(BigInteger)
    command_id = Column(BigInteger)
    parameters = Column(JSON)
    queued_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))
    is_error = Column(Boolean)
    result = Column(Text)
    status = Column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True)
    table_name = Column(Text, nullable=False)
    operation = Column(Text, nullable=False)
    row_id = Column(BigInteger, nullable=True)
    old_data = Column(JSON, nullable=True)
    new_data = Column(JSON, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())