"""
Central configuration for the web app and worker.
Both the Flask app and RQ worker use this as the single source of truth.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (parent of core/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

# Paths
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(_PROJECT_ROOT / "output")))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", str(_PROJECT_ROOT / "data" / "app.db")))

# Database: connection string for SQLAlchemy. Default SQLite; set DATABASE_URL for PostgreSQL.
# If only DATABASE_PATH is set, we build sqlite:/// from it for backward compatibility.
if os.getenv("DATABASE_URL"):
    DATABASE_URL = os.getenv("DATABASE_URL")
else:
    _db_path = Path(DATABASE_PATH).resolve()
    _db_str = _db_path.as_posix() if hasattr(_db_path, "as_posix") else str(_db_path).replace("\\", "/")
    DATABASE_URL = f"sqlite:///{_db_str}"

# Redis / RQ
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Job timeout (seconds); jobs exceeding this are failed so the worker can pick the next one.
RQ_JOB_TIMEOUT = int(os.getenv("RQ_JOB_TIMEOUT", "300"))
# Retry failed jobs: max attempts and intervals (seconds) between retries (exponential backoff).
RQ_RETRY_MAX = int(os.getenv("RQ_RETRY_MAX", "3"))
_rq_intervals = os.getenv("RQ_RETRY_INTERVALS", "60,120,300")
RQ_RETRY_INTERVALS = [int(x.strip()) for x in _rq_intervals.split(",") if x.strip()]

# Pipeline defaults
REVIEWS_LIMIT = int(os.getenv("REVIEWS_LIMIT", "200"))
