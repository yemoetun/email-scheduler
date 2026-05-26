"""
main.py
-------
FastAPI application with four main areas of responsibility:

  1. GOOGLE OAUTH  (/auth/login, /auth/callback, /auth/me, /auth/logout)
     - Redirects the user to Google's consent screen
     - Handles the callback, exchanges the code for tokens
     - Returns user info to the frontend

  2. AI GENERATION  (/generate)
     - Accepts a short prompt from the user
     - Sends it to the Gemini API with a "professional email assistant" system prompt
     - Returns the generated email text

  3. SCHEDULING  (/schedule)
     - Saves the final email payload + OAuth tokens to SQLite
     - The background worker in scheduler.py picks it up when the time comes

  4. JOB STATUS  (/jobs)
     - Lists all scheduled emails for the logged-in user
"""

import os
import json
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from dotenv import load_dotenv

from database import init_db, get_db, ScheduledEmail, JobStatus
from scheduler import start_scheduler, stop_scheduler

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Environment variables ──────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY         = os.getenv("GROQ_API_KEY")
SECRET_KEY           = os.getenv("SECRET_KEY", "change_me")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Google OAuth endpoints
GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v1/userinfo"

# Groq API endpoint (free, fast, uses Llama 3)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# ── App setup ─────────────────────────────────────────────────────────────────
app = FastAPI(title="Email Scheduler API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await init_db()       # Create DB tables if they don't exist
    start_scheduler()     # Start the background email worker


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()


# ── In-memory session store (simple MVP approach) ─────────────────────────────
# For production you'd use Redis or signed JWTs.
# Key = session_id (stored in a cookie), Value = user data dict
sessions: dict[str, dict] = {}


def get_session(request: Request) -> Optional[dict]:
    """Read the current user's session from the cookie."""
    sid = request.cookies.get("session_id")
    return sessions.get(sid) if sid else None


# ══════════════════════════════════════════════════════════════════════════════
# 1. GOOGLE OAUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/auth/login")
def login():
    """
    Step 1 of OAuth: redirect the browser to Google's consent screen.
    We request two scopes:
      - 'openid email profile' → to know who the user is
      - 'gmail.send'           → to send emails on their behalf
    'access_type=offline' ensures we get a refresh_token so we can
    send emails later even if the user's browser tab is closed.
    """
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile https://www.googleapis.com/auth/gmail.send",
        "access_type":   "offline",
        "prompt":        "consent",   # Force consent so we always get refresh_token
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{query}")


@app.get("/auth/callback")
async def auth_callback(code: str, request: Request):
    """
    Step 2 of OAuth: Google redirects back here with a one-time 'code'.
    We exchange it for access_token + refresh_token, then fetch user info.
    """
    async with httpx.AsyncClient() as client:
        # Exchange code → tokens
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        })
        token_data = token_resp.json()

        if "error" in token_data:
            raise HTTPException(400, f"OAuth error: {token_data['error_description']}")

        access_token  = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in    = token_data.get("expires_in", 3600)

        # Fetch user profile
        user_resp = await client.get(
            GOOGLE_USERINFO,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_info = user_resp.json()

    # Store session server-side
    import secrets
    sid = secrets.token_hex(32)
    sessions[sid] = {
        "email":         user_info["email"],
        "name":          user_info.get("name", ""),
        "picture":       user_info.get("picture", ""),
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_in":    expires_in,
    }

    # Redirect to frontend with session cookie
    response = RedirectResponse(url=FRONTEND_URL)
    response.set_cookie(
        "session_id", sid,
        httponly=True,   # Not accessible via JS (security)
        samesite="lax",
        max_age=3600,
    )
    return response


@app.get("/auth/me")
def get_me(request: Request):
    """Returns the logged-in user's public info (email, name, picture)."""
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not logged in")
    return {
        "email":   session["email"],
        "name":    session["name"],
        "picture": session["picture"],
    }


@app.post("/auth/logout")
def logout(request: Request):
    """Clears the server-side session."""
    sid = request.cookies.get("session_id")
    if sid and sid in sessions:
        del sessions[sid]
    response = JSONResponse({"message": "Logged out"})
    response.delete_cookie("session_id")
    return response


# ══════════════════════════════════════════════════════════════════════════════
# 2. AI GENERATION ROUTE
# ══════════════════════════════════════════════════════════════════════════════

class GenerateRequest(BaseModel):
    prompt: str   # Short description typed by the user, e.g. "ask my boss for a day off"


@app.post("/generate")
async def generate_email(body: GenerateRequest, request: Request):
    """
    Sends the user's short prompt to Groq (Llama 3) with a strict system instruction.
    Returns a ready-to-send professional email as plain text.

    The response includes both a suggested subject line and the email body,
    separated by '---BODY---' so the frontend can split them.
    """
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not logged in")

    system_instruction = (
        "You are a professional email writing assistant. "
        "The user will give you a short description of what they want to say. "
        "Your job is to write a complete, professional email. "
        "Format your response EXACTLY like this:\n"
        "SUBJECT: <subject line here>\n"
        "---BODY---\n"
        "<email body here>\n\n"
        "Do not include any explanation or extra text outside this format."
    )

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user",   "content": body.prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GROQ_URL,
            json=payload,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        )
        data = resp.json()

    if "error" in data:
        raise HTTPException(500, f"Groq error: {data['error'].get('message', 'Unknown')}")

    try:
        generated_text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise HTTPException(500, "Unexpected response from Groq")

    # Parse subject and body
    subject, body_text = "", generated_text
    if "---BODY---" in generated_text:
        parts = generated_text.split("---BODY---", 1)
        subject_line = parts[0].strip()
        if subject_line.startswith("SUBJECT:"):
            subject = subject_line[len("SUBJECT:"):].strip()
        body_text = parts[1].strip()

    return {"subject": subject, "body": body_text}


# ══════════════════════════════════════════════════════════════════════════════
# 3. SCHEDULING ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/schedule")
async def schedule_email(
    request: Request,
    db: AsyncSession = Depends(get_db),
    recipient: str = Form(...),
    cc: str = Form(""),
    subject: str = Form(...),
    body: str = Form(...),
    scheduled_time: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    """
    Saves the email job to the database, including any uploaded attachments.
    The background worker (scheduler.py) will send it at the right time.
    """
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not logged in")

    # Parse the scheduled time (frontend sends local ISO string)
    try:
        scheduled_dt = datetime.fromisoformat(scheduled_time)
        if scheduled_dt.tzinfo is not None:
            scheduled_dt = scheduled_dt.astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(400, "Invalid scheduled_time format. Use ISO 8601.")

    if scheduled_dt <= datetime.utcnow():
        raise HTTPException(400, "Scheduled time must be in the future.")

    # Read and encode attachments as base64
    attachments = []
    for f in files:
        if f.filename:
            data = await f.read()
            attachments.append({
                "filename": f.filename,
                "mime_type": f.content_type or "application/octet-stream",
                "data_b64": base64.b64encode(data).decode("utf-8"),
            })

    job = ScheduledEmail(
        recipient=recipient,
        cc=cc,
        subject=subject,
        body=body,
        scheduled_time=scheduled_dt,
        access_token=session["access_token"],
        refresh_token=session.get("refresh_token"),
        sender_email=session["email"],
        status=JobStatus.PENDING,
        attachments=json.dumps(attachments) if attachments else None,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {
        "message": "Email scheduled successfully!",
        "job_id": job.id,
        "scheduled_time": scheduled_dt.isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. JOB STATUS ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/jobs")
async def list_jobs(request: Request, db: AsyncSession = Depends(get_db)):
    """Returns all scheduled email jobs for the logged-in user."""
    session = get_session(request)
    if not session:
        raise HTTPException(401, "Not logged in")

    result = await db.execute(
        select(ScheduledEmail)
        .where(ScheduledEmail.sender_email == session["email"])
        .order_by(ScheduledEmail.scheduled_time.desc())
    )
    jobs = result.scalars().all()

    return [
        {
            "id":             j.id,
            "recipient":      j.recipient,
            "cc":             j.cc,
            "subject":        j.subject,
            "scheduled_time": j.scheduled_time.isoformat(),
            "status":         j.status,
            "error_message":  j.error_message,
        }
        for j in jobs
    ]


@app.get("/")
def root():
    return {"message": "Email Scheduler API is running ✅"}
