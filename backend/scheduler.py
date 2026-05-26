"""
scheduler.py
------------
Background worker powered by APScheduler.

How it works:
  1. APScheduler runs 'check_and_send_emails()' every 60 seconds.
  2. That function queries the DB for all PENDING emails whose
     scheduled_time is in the past (i.e., due now or overdue).
  3. For each due email it:
       a. Rebuilds the user's Google credentials from stored tokens.
       b. Constructs a MIME email message.
       c. Sends it through the Gmail API (from the user's own account).
       d. Marks the job as SENT (or FAILED if something goes wrong).
"""

import base64
import json
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy import select

from database import AsyncSessionLocal, JobStatus, ScheduledEmail

logger = logging.getLogger(__name__)

# One scheduler instance shared across the app
scheduler = AsyncIOScheduler()


def _build_gmail_service(job: ScheduledEmail):
    """
    Reconstruct a Gmail API service object from the stored OAuth tokens.
    Also refreshes the access token automatically if it has expired.
    """
    creds = Credentials(
        token=job.access_token,
        refresh_token=job.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=None,   # Not needed for refresh when we have refresh_token
        client_secret=None,
    )
    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _create_mime_message(sender: str, to: str, cc: str, subject: str, body: str) -> str:
    """
    Build a MIME email and encode it as base64url (what Gmail API expects).
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw


async def check_and_send_emails():
    """
    Called every 60 seconds by APScheduler.
    Finds all due PENDING jobs and sends them.
    """
    now = datetime.utcnow()
    logger.info(f"[Scheduler] Checking for due emails at {now.isoformat()}")

    async with AsyncSessionLocal() as db:
        # Fetch all pending jobs whose scheduled time has passed
        result = await db.execute(
            select(ScheduledEmail).where(
                ScheduledEmail.status == JobStatus.PENDING,
                ScheduledEmail.scheduled_time <= now,
            )
        )
        due_jobs = result.scalars().all()
        logger.info(f"[Scheduler] Found {len(due_jobs)} due job(s)")

        for job in due_jobs:
            try:
                service = _build_gmail_service(job)
                raw_message = _create_mime_message(
                    sender=job.sender_email,
                    to=job.recipient,
                    cc=job.cc or "",
                    subject=job.subject,
                    body=job.body,
                )
                service.users().messages().send(
                    userId="me",
                    body={"raw": raw_message},
                ).execute()

                job.status = JobStatus.SENT
                logger.info(f"[Scheduler] ✅ Sent email job #{job.id} to {job.recipient}")

            except Exception as e:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                logger.error(f"[Scheduler] ❌ Failed job #{job.id}: {e}")

        await db.commit()


def start_scheduler():
    """Register the job and start the scheduler. Called once at app startup."""
    scheduler.add_job(
        check_and_send_emails,
        trigger="interval",
        seconds=60,
        id="email_worker",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[Scheduler] Started — checking for emails every 60 seconds")


def stop_scheduler():
    """Gracefully shut down the scheduler. Called at app shutdown."""
    scheduler.shutdown(wait=False)
    logger.info("[Scheduler] Stopped")
