import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.engine import URL


def get_env(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

engine = create_engine(
    URL.create(
        drivername="postgresql",
        username=get_env("DB_USER"),
        password=get_env("DB_BACKEND_PASSWORD"),
        host=get_env("POSTGRES_HOST"),
        port=get_env("POSTGRES_PORT"),
        database=get_env("POSTGRES_DB"),
    ),
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
