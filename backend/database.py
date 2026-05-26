"""
database.py
-----------
Sets up the SQLite database using SQLAlchemy (async).

The 'scheduled_emails' table stores one row per scheduled email job.
Each row holds:
  - who to send to (recipient, cc)
  - the email body
  - when to send it (scheduled_time)
  - the user's Gmail OAuth tokens so the worker can send on their behalf
  - a status flag so we know if the job is pending, sent, or failed
"""

import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, Enum as SAEnum
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv
import enum

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./email_scheduler.db")

# Create the async database engine (SQLite file is created automatically)
engine = create_async_engine(DATABASE_URL, echo=False)

# Session factory — used inside route handlers to talk to the DB
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ScheduledEmail(Base):
    """One row = one scheduled email job."""
    __tablename__ = "scheduled_emails"

    id = Column(Integer, primary_key=True, index=True)

    # Who the email goes to
    recipient = Column(String, nullable=False)          # "To" field
    cc = Column(String, nullable=True)                  # "CC" field (optional)

    # Email content
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)

    # When to fire
    scheduled_time = Column(DateTime, nullable=False)

    # Gmail OAuth credentials for this specific user
    # Stored as JSON strings so the worker can authenticate as them
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)

    # Which Gmail account is sending
    sender_email = Column(String, nullable=False)

    # Job lifecycle
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text, nullable=True)   # filled in if the job fails


async def init_db():
    """Create all tables if they don't exist yet. Called once at startup."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI dependency — yields a DB session and closes it after the request."""
    async with AsyncSessionLocal() as session:
        yield session
