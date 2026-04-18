import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
POSTGRES_DB = os.getenv("POSTGRES_DB", "sicc")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

# Prefer IoT-specific DB credentials when provided
DB_USER = os.getenv("DB_IOT_USER") or POSTGRES_USER
DB_PASSWORD = os.getenv("DB_IOT_PASSWORD") or POSTGRES_PASSWORD

DATABASE_URL = os.getenv("DATABASE_URL") or (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    # Only create tables when running as the DB superuser or when explicitly
    # requested via INIT_DB. Application roles should not attempt DDL.
    init_flag = os.getenv("INIT_DB", "false").lower() in ("1", "true", "yes")
    if DB_USER == POSTGRES_USER or init_flag:
        Base.metadata.create_all(bind=engine)
