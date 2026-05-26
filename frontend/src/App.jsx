/**
 * App.jsx
 * -------
 * Root component. Handles two states:
 *   - Not logged in → shows the Login screen
 *   - Logged in     → shows the Email Composer + Scheduled Jobs list
 *
 * All API calls go through api.js. No external UI library is used —
 * everything is styled with index.css.
 */

import { useState, useEffect, useCallback } from "react";
import { getMe, loginWithGoogle, logout, generateEmail, scheduleEmail, getJobs } from "./api";

// ── Small helper components ────────────────────────────────────────────────

function Badge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

function Alert({ type, message, onClose }) {
  if (!message) return null;
  return (
    <div className={`alert alert-${type}`}>
      {message}
      {onClose && (
        <button
          onClick={onClose}
          style={{ float: "right", background: "none", border: "none", cursor: "pointer", fontWeight: "bold" }}
        >
          ✕
        </button>
      )}
    </div>
  );
}

// ── Login Screen ───────────────────────────────────────────────────────────

function LoginScreen() {
  return (
    <div className="login-screen">
      {/* Simple envelope SVG icon */}
      <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
        <rect width="64" height="64" rx="16" fill="#ebf8ff"/>
        <path d="M12 20h40v28H12z" fill="#bee3f8" stroke="#4299e1" strokeWidth="2"/>
        <path d="M12 20l20 16 20-16" stroke="#4299e1" strokeWidth="2" fill="none"/>
      </svg>

      <h1>Email Scheduler</h1>
      <p>
        Write AI-powered emails and schedule them to send at exactly the right time —
        straight from your own Gmail account.
      </p>

      <button className="btn btn-google" onClick={loginWithGoogle}>
        {/* Google logo inline SVG */}
        <svg className="google-icon" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
        Sign in with Google
      </button>
    </div>
  );
}

// ── Scheduled Jobs Panel ───────────────────────────────────────────────────

function JobsPanel() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await getJobs();
      setJobs(data);
    } catch {
      // silently ignore — user may not have any jobs yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return null;
  if (jobs.length === 0) return null;

  return (
    <div className="card">
      <h2>📬 Scheduled Emails</h2>
      <table className="jobs-table">
        <thead>
          <tr>
            <th>To</th>
            <th>Subject</th>
            <th>Scheduled For</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((j) => (
            <tr key={j.id}>
              <td>{j.recipient}</td>
              <td>{j.subject}</td>
              <td>{new Date(j.scheduled_time).toLocaleString()}</td>
              <td><Badge status={j.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Email Composer ────────────────────────────────────────────────────

function EmailComposer({ user, onLogout }) {
  // Form fields
  const [to, setTo]             = useState("");
  const [cc, setCc]             = useState("");
  const [prompt, setPrompt]     = useState("");
  const [subject, setSubject]   = useState("");
  const [body, setBody]         = useState("");
  const [scheduleAt, setScheduleAt] = useState("");

  // UI state
  const [generating, setGenerating]   = useState(false);
  const [scheduling, setScheduling]   = useState(false);
  const [alert, setAlert]             = useState({ type: "", message: "" });
  const [jobsKey, setJobsKey]         = useState(0); // increment to refresh jobs

  const clearAlert = () => setAlert({ type: "", message: "" });

  // ── Generate email via Gemini ──────────────────────────────
  const handleGenerate = async () => {
    if (!prompt.trim()) {
      setAlert({ type: "error", message: "Please enter a description first." });
      return;
    }
    setGenerating(true);
    clearAlert();
    try {
      const result = await generateEmail(prompt.trim());
      setSubject(result.subject || "");
      setBody(result.body || "");
    } catch (err) {
      setAlert({ type: "error", message: `Generation failed: ${err.message}` });
    } finally {
      setGenerating(false);
    }
  };

  // ── Schedule the email ─────────────────────────────────────
  const handleSchedule = async () => {
    if (!to.trim())         return setAlert({ type: "error", message: "Please fill in the 'To' field." });
    if (!subject.trim())    return setAlert({ type: "error", message: "Subject is empty — generate or type one first." });
    if (!body.trim())       return setAlert({ type: "error", message: "Email body is empty." });
    if (!scheduleAt)        return setAlert({ type: "error", message: "Please pick a date and time to schedule." });

    setScheduling(true);
    clearAlert();
    try {
      const result = await scheduleEmail({
        recipient: to.trim(),
        cc: cc.trim(),
        subject: subject.trim(),
        body: body.trim(),
        scheduled_time: new Date(scheduleAt).toISOString(),
      });
      setAlert({ type: "success", message: `✅ Email scheduled for ${new Date(scheduleAt).toLocaleString()}` });
      // Reset form
      setTo(""); setCc(""); setPrompt(""); setSubject(""); setBody(""); setScheduleAt("");
      setJobsKey(k => k + 1); // refresh jobs table
    } catch (err) {
      setAlert({ type: "error", message: `Scheduling failed: ${err.message}` });
    } finally {
      setScheduling(false);
    }
  };

  // Build the minimum datetime string for the picker (now + 1 min)
  const minDatetime = new Date(Date.now() + 60000).toISOString().slice(0, 16);

  return (
    <>
      {/* Header */}
      <div className="app-header">
        <h1>✉️ Email Scheduler</h1>
        <div className="user-info">
          {user.picture && <img src={user.picture} alt={user.name} />}
          <span>{user.name || user.email}</span>
          <button className="btn btn-logout" onClick={onLogout}>Sign out</button>
        </div>
      </div>

      {/* Alert banner */}
      <Alert type={alert.type} message={alert.message} onClose={clearAlert} />

      {/* ── Step 1: Recipients ── */}
      <div className="card">
        <h2>1. Recipients</h2>
        <div className="row">
          <div className="field">
            <label>To *</label>
            <input
              type="email"
              placeholder="recipient@example.com"
              value={to}
              onChange={e => setTo(e.target.value)}
            />
          </div>
          <div className="field">
            <label>CC (optional)</label>
            <input
              type="email"
              placeholder="cc@example.com"
              value={cc}
              onChange={e => setCc(e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* ── Step 2: AI Generation ── */}
      <div className="card">
        <h2>2. Generate Email with AI</h2>
        <div className="field">
          <label>Describe your email</label>
          <textarea
            placeholder='e.g. "Ask my manager if I can take Friday off for a dentist appointment"'
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            style={{ minHeight: "80px" }}
          />
        </div>
        <button
          className="btn btn-primary"
          onClick={handleGenerate}
          disabled={generating}
        >
          {generating ? <><span className="spinner" /> Generating…</> : "✨ Generate Email"}
        </button>
      </div>

      {/* ── Step 3: Review & Edit ── */}
      <div className="card">
        <h2>3. Review & Edit</h2>
        <div className="field">
          <label>Subject</label>
          <input
            type="text"
            placeholder="Subject will appear here after generation"
            value={subject}
            onChange={e => setSubject(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Email Body (editable)</label>
          <textarea
            className="output"
            placeholder="Your generated email will appear here. You can edit it before scheduling."
            value={body}
            onChange={e => setBody(e.target.value)}
          />
        </div>
      </div>

      {/* ── Step 4: Schedule ── */}
      <div className="card">
        <h2>4. Schedule</h2>
        <div className="field" style={{ maxWidth: "300px" }}>
          <label>Send at</label>
          <input
            type="datetime-local"
            value={scheduleAt}
            min={minDatetime}
            onChange={e => setScheduleAt(e.target.value)}
          />
        </div>
        <button
          className="btn btn-success"
          onClick={handleSchedule}
          disabled={scheduling}
          style={{ marginTop: "0.5rem" }}
        >
          {scheduling ? <><span className="spinner" /> Scheduling…</> : "📅 Schedule Email"}
        </button>
      </div>

      {/* ── Scheduled jobs list ── */}
      <JobsPanel key={jobsKey} />
    </>
  );
}

// ── Root App ───────────────────────────────────────────────────────────────

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = loading, null = not logged in

  useEffect(() => {
    getMe().then(setUser);
  }, []);

  const handleLogout = async () => {
    await logout();
    setUser(null);
  };

  // Still checking auth status
  if (user === undefined) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
        <div className="spinner" style={{ borderColor: "rgba(66,153,225,0.3)", borderTopColor: "#4299e1", width: 32, height: 32 }} />
      </div>
    );
  }

  return (
    <div className="app-container">
      {user ? (
        <EmailComposer user={user} onLogout={handleLogout} />
      ) : (
        <LoginScreen />
      )}
    </div>
  );
}
