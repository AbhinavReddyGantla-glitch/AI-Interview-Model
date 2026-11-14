from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typing import Generator
from app.core.config import settings

# Create sync engine
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# Session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get db session in FastAPI path operations
def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
