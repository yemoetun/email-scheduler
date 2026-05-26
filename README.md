# Email Scheduler

A full-stack app that lets you write AI-generated emails and schedule them to send at a future time — straight from your own Gmail account.

**Tech stack:** FastAPI · SQLite · APScheduler · React (Vite) · Groq (Llama 3) · Google OAuth

---

## Project Structure

```
Email_Automation/
├── backend/
│   ├── main.py           # FastAPI app — all routes (OAuth, AI, scheduling)
│   ├── database.py       # SQLite schema & session factory
│   ├── scheduler.py      # Background worker that fires emails on time
│   ├── requirements.txt  # Python dependencies
│   └── .env.example      # Template — copy to .env and fill in your keys
└── frontend/
    ├── src/
    │   ├── App.jsx       # Main UI (login, compose, schedule, job list)
    │   ├── api.js        # All HTTP calls to the backend
    │   └── index.css     # Styles
    ├── index.html
    ├── vite.config.js
    └── package.json
```

---

## Prerequisites

- Python 3.10 or higher
- Node.js 18 or higher
- A Google account

---

## Step 1 — Get a Free Groq API Key (AI generation)

Groq is free with no credit card required.

1. Go to https://console.groq.com and sign up
2. Click **API Keys** in the left sidebar
3. Click **Create API Key**, give it any name
4. Copy the key (starts with `gsk_...`)

---

## Step 2 — Set Up Google Cloud (OAuth + Gmail API)

This lets users log in with Google and send emails from their own Gmail account.

**2a — Create a project:**
1. Go to https://console.cloud.google.com
2. Click the project dropdown at the top → **New Project**
3. Name it `Email Scheduler` → **Create**

**2b — Enable the Gmail API:**
1. Go to **APIs & Services → Library**
2. Search for `Gmail API` → click it → click **Enable**

**2c — Set up OAuth consent screen:**
1. Go to **APIs & Services → OAuth consent screen** (or **Google Auth Platform → Audience**)
2. Choose **External** → **Create**
3. Fill in App name (`Email Scheduler`), your email for support and developer contact
4. Click through to **Test users** → **Add Users** → enter your Gmail address → **Save**

**2d — Create OAuth credentials:**
1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → OAuth 2.0 Client IDs**
3. Application type: **Web application**
4. Name: `Email Scheduler Local`
5. Under **Authorized redirect URIs** add: `http://localhost:8000/auth/callback`
6. Click **Create**
7. Copy the **Client ID** and **Client Secret** from the popup

---

## Step 3 — Configure Your Environment File

```bash
cd backend
cp .env.example .env
```

Open `backend/.env` in any text editor and replace each value:

```env
# ── Google OAuth ──────────────────────────────────────────────
# From Google Cloud Console → Credentials → your OAuth 2.0 Client ID
GOOGLE_CLIENT_ID=paste_your_client_id_here
GOOGLE_CLIENT_SECRET=paste_your_client_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback

# ── Groq AI ───────────────────────────────────────────────────
# From https://console.groq.com/keys
GROQ_API_KEY=paste_your_groq_key_here

# ── App Security ──────────────────────────────────────────────
# Generate a random secret with:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=paste_a_long_random_string_here

# ── Database ──────────────────────────────────────────────────
# SQLite file — created automatically on first run, no setup needed
DATABASE_URL=sqlite+aiosqlite:///./email_scheduler.db

# ── Frontend URL ──────────────────────────────────────────────
FRONTEND_URL=http://localhost:5173
```

> **Never commit your `.env` file.** It is listed in `.gitignore` and will not be pushed to GitHub.

---

## Step 4 — Run the Backend

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt
pip install greenlet             # Required for SQLAlchemy async on Python 3.12+

# Start the server
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     [Scheduler] Started — checking for emails every 60 seconds
```

Visit http://localhost:8000 — you should see `{"message":"Email Scheduler API is running ✅"}`

---

## Step 5 — Run the Frontend

Open a **second terminal** (keep the backend running in the first):

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

---

## How to Use the App

1. Click **Sign in with Google** and approve the permissions
2. Fill in the **To** field (and optionally CC)
3. Type a short description in the **Describe your email** box
   - e.g. *"Ask my manager if I can take Friday off"*
4. Click **✨ Generate Email** — Llama 3 writes a professional email
5. Edit the subject or body if you want to tweak anything
6. Pick a **date and time** to send it
7. Click **📅 Schedule Email**

The email sends from your own Gmail at the scheduled time, even if you close the browser (as long as the backend is still running).

> **Note:** This app runs on a local server. The scheduler only works while the backend is running on your machine. If you stop the server, scheduled emails will not be sent — but they are saved in the database and will send as soon as you restart the server. If you want the scheduler to run 24/7 without keeping your computer on, see the [Deployment](#deployment) section below.

---

---

## Deployment

This project is designed to run locally. If you want it running 24/7 so emails always send on time (even when your computer is off), you can deploy it to a cloud server.

**Free options:**

| Platform | Free Tier | Notes |
|---|---|---|
| [Railway](https://railway.app) | $5 credit/month | Easiest setup, deploys from GitHub |
| [Render](https://render.com) | Free web service | Spins down after 15 min inactivity |
| [Fly.io](https://fly.io) | Generous free tier | Never sleeps, slightly more setup |

**Important:** SQLite does not persist on most cloud platforms (the filesystem resets on redeploy). Before deploying you will need to swap the database to a hosted PostgreSQL instance — [Supabase](https://supabase.com) offers a free Postgres database that works well with this stack.

The core changes needed for deployment are:
1. Replace `sqlite+aiosqlite:///./email_scheduler.db` in `DATABASE_URL` with a Postgres connection string
2. Add a `Procfile` or `railway.json` config pointing to `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Set all your `.env` variables as environment variables in the platform's dashboard
4. Update `GOOGLE_REDIRECT_URI` and `FRONTEND_URL` to your deployed URLs
5. Add the new redirect URI to your Google Cloud OAuth credentials

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Access blocked` on Google login | Go to Google Cloud → OAuth consent screen → Audience → add your Gmail as a test user |
| `redirect_uri_mismatch` | Make sure the redirect URI in Google Cloud Console exactly matches `http://localhost:8000/auth/callback` |
| `Generation failed: Not logged in` | Your session expired — refresh the page and sign in again |
| Groq returns an error | Check your `GROQ_API_KEY` in `backend/.env` |
| Email not sending | Check the backend terminal for scheduler error logs |
| `ModuleNotFoundError` | Make sure your virtual environment is activated: `source venv/bin/activate` |
| `greenlet` error on startup | Run `pip install greenlet` inside your virtual environment |
