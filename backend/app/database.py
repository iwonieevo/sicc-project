import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# Prefer backend-specific DB credentials when available
DB_ENV = {
    "NAME": os.getenv("POSTGRES_DB"),
    "HOST": os.getenv("POSTGRES_HOST"),
    "PORT": os.getenv("POSTGRES_PORT"),
    "USER": os.getenv("DB_BACKEND_USER", os.getenv("POSTGRES_USER")),
    "PASSWORD": os.getenv("DB_BACKEND_PASSWORD", os.getenv("POSTGRES_PASSWORD"))
}

if None in DB_ENV.values():
    raise RuntimeError(f"Missing required database environment variables: {', '.join(name for name, value in DB_ENV.items() if value is None)}")

DATABASE_URL = f"postgresql://{DB_ENV['USER']}:{DB_ENV['PASSWORD']}@{DB_ENV['HOST']}:{DB_ENV['PORT']}/{DB_ENV['NAME']}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
