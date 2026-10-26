from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_size=5,
    max_overflow=5,
    pool_timeout=5,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
