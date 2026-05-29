import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


def get_env(name: str) -> str:
    """Strictly fetches an environment variable or halts execution if missing."""
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


connect_args = {"sslmode": os.getenv("DB_SSLMODE", "verify-full")}

if sslrootcert := os.getenv("DB_SSLROOTCERT"):
    connect_args["sslrootcert"] = sslrootcert

engine = create_engine(
    URL.create(
        drivername="postgresql",
        username=get_env("DB_USER"),
        password=get_env("DB_BACKEND_PASSWORD"),
        host=get_env("POSTGRES_HOST"),
        port=get_env("POSTGRES_PORT"),
        database=get_env("POSTGRES_DB"),
    ),
    connect_args=connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Modern declarative base class for all database models."""

    pass


def get_db() -> Generator[Session, None, None]:
    """Yields a database session scoped to a single request, ensuring clean teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
