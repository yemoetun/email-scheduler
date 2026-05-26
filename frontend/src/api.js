/**
 * api.js
 * ------
 * Central place for all HTTP calls to the FastAPI backend.
 * Every function uses the Fetch API with credentials: "include"
 * so the session cookie is automatically sent with every request.
 *
 * The Vite proxy (vite.config.js) rewrites /api/* → http://localhost:8000/*
 * so we never have to worry about CORS during local development.
 */

const BASE = "/api";

async function handleResponse(res) {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return res.json();
}

/** Fetch the currently logged-in user (or null if not logged in). */
export async function getMe() {
  const res = await fetch(`${BASE}/auth/me`, { credentials: "include" });
  if (res.status === 401) return null;
  return handleResponse(res);
}

/** Kick off Google OAuth — navigates the browser to the backend login route. */
export function loginWithGoogle() {
  window.location.href = `${BASE}/auth/login`;
}

/** Log out and clear the session cookie. */
export async function logout() {
  await fetch(`${BASE}/auth/logout`, { method: "POST", credentials: "include" });
}

/**
 * Ask the backend to generate an email from a short prompt.
 * @param {string} prompt  e.g. "ask my manager for a day off next Friday"
 * @returns {{ subject: string, body: string }}
 */
export async function generateEmail(prompt) {
  const res = await fetch(`${BASE}/generate`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  return handleResponse(res);
}

/**
 * Schedule an email to be sent at a future time.
 * @param {{ recipient, cc, subject, body, scheduled_time }} payload
 * @returns {{ message, job_id, scheduled_time }}
 */
export async function scheduleEmail(payload) {
  const res = await fetch(`${BASE}/schedule`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse(res);
}

/** Fetch all scheduled jobs for the logged-in user. */
export async function getJobs() {
  const res = await fetch(`${BASE}/jobs`, { credentials: "include" });
  return handleResponse(res);
}
