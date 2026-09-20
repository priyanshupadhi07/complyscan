import os
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Ensure backend and root paths are resolvable
backend_dir = Path(__file__).resolve().parent
root_dir = backend_dir.parent

for path in (str(backend_dir), str(root_dir)):
    if path not in sys.path:
        sys.path.append(path)

# 2. Dynamic model import for root and nested module contexts
try:
    from backend.models import Base
except ImportError:
    from models import Base

# 3. Environment-aware SQLite path (uses /tmp on Vercel, project dir on local)
if os.getenv("VERCEL"):
    DATABASE_URL = "sqlite:////tmp/compliance.db"
else:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./compliance.db")

# 4. Engine & Session configuration
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


def create_tables():
    """
    Create all tables defined in models.py.
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    """
    Create and return a database session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()