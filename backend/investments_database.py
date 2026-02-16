"""
Database setup for the investments SQLite database.
Separate from the main budget.db to isolate investment data.
Lives at ~/BudgetApp/investments.db.
"""

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Database location: ~/BudgetApp/investments.db
DB_DIR = Path.home() / "BudgetApp"
DB_DIR.mkdir(exist_ok=True)
DB_PATH = DB_DIR / "investments.db"

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,
    },
    echo=False,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_investments_db():
    """FastAPI dependency that provides an investments database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_investments_db():
    """Create all investment tables if they don't exist."""
    from . import models_investments  # noqa: F401
    Base.metadata.create_all(bind=engine)
