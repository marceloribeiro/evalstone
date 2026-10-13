"""Preloaded IPython console: `just console`. Arrow-up history comes with IPython."""

from sqlalchemy import select, text  # noqa: F401

from app import tasks  # noqa: F401
from app.config import get_settings  # noqa: F401
from app.db import SessionLocal
from app.models import *  # noqa: F403

db = SessionLocal()
print("evalstone-api console — `db` session, models, `tasks`, `select`, `text` loaded")
