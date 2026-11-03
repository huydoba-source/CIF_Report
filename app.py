"""
CIF Compliance Report — Streamlit web app.

Flow: Upload CSV -> Validate file -> Process & write to Google Sheets (live progress + log) -> Result.
Processing logic lives in cif_pipeline.py; this file only handles the UI/UX.
"""

from __future__ import annotations

import hmac
import html
import io
import time
from datetime import datetime

import pandas as pd
import streamlit as st

import cif_pipeline as cp

st.set_page_config(
    page_title="CIF Compliance Report",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ==========================================
# STYLE
# ==========================================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #f5f5f7;
  --card: #ffffff;
  --text: #1d1d1f;
  --muted: #6e6e73;
  --subtle: #86868b;
  --line: rgba(0, 0, 0, 0.07);
  --accent: #0071e3;
  --accent-2: #5e5ce6;
  --success: #30d158;
  --success-ink: #248a3d;
  --warning: #ff9f0a;
  --error: #ff3b30;
  --radius: 22px;
  --shadow: 0 1px 2px rgba(0,0,0,.04), 0 8px 28px rgba(0,0,0,.06);
  --ease: cubic-bezier(.2, .8, .2, 1);
}

html, body, .stApp { background: var(--bg); }
.stApp, .stApp p, .stApp label, .stApp input, .stApp button {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stMainBlockContainer"], .block-container { max-width: 780px; padding-top: 2.5rem; padding-bottom: 4rem; }
footer, #MainMenu { visibility: hidden; }
[data-testid="stElementContainer"]:has(> .stHtml style) { display: none; }

/* ---------- Animations ---------- */
@keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
@keyframes growA { from { width: var(--from); } to { width: var(--to); } }
@keyframes growB { from { width: var(--from); } to { width: var(--to); } }
@keyframes shimmer { from { transform: translateX(-100%); } to { transform: translateX(100%); } }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(0,113,227,.35); } 70% { box-shadow: 0 0 0 10px rgba(0,113,227,0); } 100% { box-shadow: 0 0 0 0 rgba(0,113,227,0); } }
@keyframes lineIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: none; } }
@keyframes pop { 0% { transform: scale(.6); opacity: 0; } 60% { transform: scale(1.06); opacity: 1; } 100% { transform: scale(1); } }
.fade-up { animation: fadeUp .6s var(--ease) both; }

/* ---------- Hero ---------- */
.hero { text-align: center; margin-bottom: 1.6rem; }
.hero-badge {
  display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px; border-radius: 999px;
  background: rgba(0,113,227,.08); color: var(--accent); font-size: 12.5px; font-weight: 600; letter-spacing: .02em;
}
.hero-title {
  font-size: clamp(30px, 5vw, 44px); font-weight: 800; letter-spacing: -0.035em; line-height: 1.08;
  margin: 14px 0 10px; color: var(--text);
  background: linear-gradient(135deg, #1d1d1f 30%, #0071e3 75%, #5e5ce6 100%);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
}
.hero-sub { color: var(--muted); font-size: 16.5px; line-height: 1.55; max-width: 560px; margin: 0 auto; }

/* ---------- Stepper ---------- */
.stepper { display: flex; align-items: center; justify-content: center; gap: 0; margin: 1.8rem auto 1.6rem; max-width: 520px; }
.step { display: flex; flex-direction: column; align-items: center; gap: 8px; min-width: 88px; }
.step-dot {
  width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
  font-size: 13px; font-weight: 700; background: #e8e8ed; color: var(--subtle);
  transition: all .4s var(--ease);
}
.step-label { font-size: 12.5px; font-weight: 600; color: var(--subtle); }
.step.active .step-dot { background: var(--accent); color: #fff; animation: pulse 2s infinite; }
.step.active .step-label { color: var(--text); }
.step.done .step-dot { background: var(--success); color: #fff; }
.step.done .step-label { color: var(--text); }
.step-line { flex: 1; height: 2px; background: #e1e1e6; margin-bottom: 26px; border-radius: 2px; position: relative; overflow: hidden; }
.step-line.done::after { content: ''; position: absolute; inset: 0; background: var(--success); animation: growA .6s var(--ease) both; --from: 0%; --to: 100%; }

/* ---------- Cards (keyed Streamlit containers) ---------- */
.st-key-upload_card, .st-key-action_card, .st-key-result_card, .st-key-login_card {
  background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow);
  padding: 28px 28px 24px; border: 1px solid var(--line); animation: fadeUp .6s var(--ease) both;
}
.card-title { font-size: 19px; font-weight: 700; letter-spacing: -0.02em; color: var(--text); margin-bottom: 2px; }
.card-sub { font-size: 14px; color: var(--muted); margin-bottom: 4px; }

/* ---------- File uploader ---------- */
[data-testid="stFileUploaderDropzone"] {
  border: 1.5px dashed #c7c7cc !important; border-radius: 18px !important; background: #fbfbfd !important;
  padding: 26px 22px !important; transition: all .25s var(--ease);
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--accent) !important; background: rgba(0,113,227,.04) !important; transform: translateY(-1px); }
[data-testid="stFileUploaderDropzone"] button { border-radius: 999px !important; font-weight: 600 !important; }
[data-testid="stFileUploaderFile"] { border-radius: 14px; }

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {
  border-radius: 999px !important; font-weight: 600 !important; padding: .62rem 1.3rem !important;
  transition: transform .18s var(--ease), box-shadow .25s var(--ease), background .25s !important;
}
.stFormSubmitButton > button { border-radius: 999px !important; font-weight: 600 !important; padding: .62rem 1.3rem !important; }
[data-testid="stTextInputRootElement"] { border-radius: 14px !important; background: #f5f5f7 !important; border: 1px solid #d2d2d7 !important; transition: border-color .2s, box-shadow .2s; }
[data-testid="stTextInputRootElement"]:focus-within { border-color: var(--accent) !important; box-shadow: 0 0 0 4px rgba(0,113,227,.12); }
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"], .stLinkButton > a[kind="primary"], [data-testid="stBaseLinkButton-primary"] {
  background: linear-gradient(180deg, #1a82f7 0%, #0071e3 100%) !important; border: none !important; color: #fff !important;
  box-shadow: 0 6px 18px rgba(0,113,227,.28) !important;
}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseLinkButton-primary"]:hover { transform: translateY(-1px); box-shadow: 0 10px 26px rgba(0,113,227,.36) !important; }
[data-testid="stBaseButton-primary"]:active { transform: scale(.98); }
[data-testid="stBaseButton-primary"]:disabled { background: #d2d2d7 !important; box-shadow: none !important; color: #fff !important; }
[data-testid="stBaseButton-secondary"] { background: #fff !important; border: 1px solid #d2d2d7 !important; }
[data-testid="stBaseButton-secondary"]:hover { border-color: var(--accent) !important; color: var(--accent) !important; }

/* ---------- File summary ---------- */
.file-card { display: flex; gap: 16px; align-items: center; padding: 16px 18px; border-radius: 16px; background: #f5f5f7; margin: 6px 0 4px; animation: fadeUp .5s var(--ease) both; }
.file-icon { width: 46px; height: 46px; border-radius: 12px; display: grid; place-items: center; background: linear-gradient(135deg, #34c759, #30b0c7); color: #fff; font-weight: 800; font-size: 12px; letter-spacing: .04em; flex-shrink: 0; }
.file-name { font-weight: 650; color: var(--text); font-size: 15px; word-break: break-all; }
.file-meta { color: var(--muted); font-size: 13px; margin-top: 2px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 4px; }
.chip { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600; padding: 6px 12px; border-radius: 999px; animation: fadeUp .5s var(--ease) both; }
.chip.ok { background: rgba(48,209,88,.12); color: var(--success-ink); }
.chip.bad { background: rgba(255,59,48,.1); color: #d70015; }
.chip.info { background: rgba(0,113,227,.08); color: var(--accent); }

.action-note { font-size: 13.5px; color: var(--muted); line-height: 1.55; margin-top: 2px; }
.action-note b { color: var(--text); font-weight: 600; }
.mini-steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 14px 0 6px; }
.mini-step { background: #f5f5f7; border-radius: 14px; padding: 12px 14px; font-size: 13px; color: var(--muted); }
.mini-step b { display: block; color: var(--text); font-size: 13.5px; margin-bottom: 2px; }

/* ---------- Progress ---------- */
.prog-card { background: var(--card); border-radius: var(--radius); box-shadow: var(--shadow); border: 1px solid var(--line); padding: 26px 28px 22px; animation: fadeUp .5s var(--ease) both; }
.prog-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; }
.prog-eyebrow { font-size: 12px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: .08em; }
.prog-eyebrow.err { color: var(--error); }
.prog-eyebrow.ok { color: var(--success-ink); }
.prog-stage { font-size: 20px; font-weight: 700; letter-spacing: -0.02em; color: var(--text); margin-top: 4px; }
.prog-pct { font-size: 42px; font-weight: 800; letter-spacing: -0.04em; color: var(--text); line-height: 1; font-variant-numeric: tabular-nums; }
.prog-pct span { font-size: 20px; color: var(--subtle); margin-left: 2px; }
.bar { height: 10px; background: #ececf0; border-radius: 999px; overflow: hidden; margin: 18px 0 12px; }
.fill { position: relative; height: 100%; width: var(--to); border-radius: 999px; overflow: hidden;
  background: linear-gradient(90deg, #0071e3, #5e5ce6); animation-duration: .35s; animation-timing-function: var(--ease); animation-fill-mode: both; }
.fill::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, transparent, rgba(255,255,255,.45), transparent); animation: shimmer 1.4s infinite; }
.fill.ok { background: linear-gradient(90deg, #30d158, #34c759); }
.fill.ok::after, .fill.err::after { display: none; }
.fill.err { background: linear-gradient(90deg, #ff6961, #ff3b30); }
.prog-foot { display: flex; justify-content: space-between; color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }

.stages { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 14px; display: grid; gap: 4px; }
.stage { display: flex; align-items: center; gap: 12px; padding: 7px 4px; font-size: 14.5px; color: var(--subtle); transition: color .3s; }
.stage .ic { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; flex-shrink: 0; border: 2px solid #d2d2d7; }
.stage .meta { margin-left: auto; font-size: 12.5px; font-variant-numeric: tabular-nums; color: var(--subtle); }
.stage.running { color: var(--text); font-weight: 600; }
.stage.running .ic { border-color: rgba(0,113,227,.2); border-top-color: var(--accent); animation: spin .8s linear infinite; }
.stage.done { color: var(--text); }
.stage.done .ic { background: var(--success); border-color: var(--success); animation: pop .4s var(--ease) both; }
.stage.error { color: var(--error); font-weight: 600; }
.stage.error .ic { background: var(--error); border-color: var(--error); }

/* ---------- CSS icons (tick / cross) ---------- */
.tick { display: block; width: 5px; height: 10px; border: solid #fff; border-width: 0 2.2px 2.2px 0; transform: translateY(-1px) rotate(45deg); }
.step-dot .tick { width: 7px; height: 13px; border-width: 0 3px 3px 0; }
.cross { position: relative; display: block; width: 10px; height: 10px; }
.cross::before, .cross::after { content: ''; position: absolute; left: 50%; top: 0; width: 2.2px; height: 100%; margin-left: -1.1px; background: #fff; border-radius: 2px; }
.cross::before { transform: rotate(45deg); } .cross::after { transform: rotate(-45deg); }
.tick.big { width: 14px; height: 28px; border-color: #30d158; border-width: 0 4px 4px 0; animation: tickIn .5s .2s var(--ease) both; }
.cross.big { width: 30px; height: 30px; animation: tickIn .5s .2s var(--ease) both; }
.cross.big::before, .cross.big::after { width: 4px; margin-left: -2px; background: #ff3b30; }
@keyframes tickIn { from { opacity: 0; scale: .4; } to { opacity: 1; scale: 1; } }

/* ---------- Console ---------- */
.console { margin-top: 16px; border-radius: 16px; background: #1c1c1e; box-shadow: 0 10px 30px rgba(0,0,0,.18); overflow: hidden; animation: fadeUp .5s var(--ease) both; }
.console-bar { display: flex; align-items: center; gap: 7px; padding: 11px 14px; background: #2c2c2e; }
.dot { width: 11px; height: 11px; border-radius: 50%; }
.dot.r { background: #ff5f57; } .dot.y { background: #febc2e; } .dot.g { background: #28c840; }
.console-title { margin-left: 8px; font-size: 12px; color: #a1a1a6; font-weight: 600; }
.live { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: #30d158; font-weight: 700; letter-spacing: .08em; }
.live::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: #30d158; animation: pulse 1.6s infinite; }
.console-body { max-height: 300px; overflow-y: auto; display: flex; flex-direction: column-reverse; padding: 12px 16px 14px; }
.console-body::-webkit-scrollbar { width: 8px; } .console-body::-webkit-scrollbar-thumb { background: #48484a; border-radius: 8px; }
.ln { font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace; font-size: 12.5px; line-height: 1.75; color: #e5e5ea; white-space: pre-wrap; word-break: break-word; }
.ln .ts { color: #636366; margin-right: 10px; }
.ln.success { color: #30d158; } .ln.error { color: #ff6961; } .ln.warning { color: #ffd60a; }
.ln.new { animation: lineIn .35s var(--ease) both; }
.ln.cursor::after { content: '▍'; color: #0a84ff; animation: pulse 1s infinite; margin-left: 2px; }

/* ---------- Result ---------- */
.result-head { text-align: center; padding: 6px 0 10px; }
.check-wrap { width: 76px; height: 76px; margin: 0 auto 14px; border-radius: 50%; background: rgba(48,209,88,.12); display: grid; place-items: center; animation: pop .6s var(--ease) both; }
.check-wrap.err { background: rgba(255,59,48,.1); }
.result-title { font-size: 26px; font-weight: 800; letter-spacing: -0.03em; color: var(--text); }
.result-sub { color: var(--muted); font-size: 15px; margin-top: 4px; }
.result-sub b { color: var(--text); }
.metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0 18px; }
.metric { background: #f5f5f7; border-radius: 16px; padding: 16px 16px 14px; animation: fadeUp .5s var(--ease) both; }
.metric .v { font-size: 24px; font-weight: 800; letter-spacing: -0.03em; color: var(--text); font-variant-numeric: tabular-nums; }
.metric .k { font-size: 12.5px; color: var(--muted); font-weight: 500; margin-top: 2px; }
.metric.hl { background: linear-gradient(135deg, rgba(0,113,227,.1), rgba(94,92,230,.1)); }
.metric.hl .v { color: var(--accent); }
.metric.warn .v { color: #c93400; }
.err-box { background: rgba(255,59,48,.06); border: 1px solid rgba(255,59,48,.18); color: #b3261e; border-radius: 14px; padding: 14px 16px; font-size: 14px; line-height: 1.5; margin: 14px 0; word-break: break-word; }

.foot { text-align: center; color: var(--subtle); font-size: 12.5px; margin-top: 2.2rem; line-height: 1.7; }
.foot a, .action-note a { color: var(--accent); text-decoration: none; font-weight: 500; }
.foot a:hover, .action-note a:hover { text-decoration: underline; }
.foot code { background: #e8e8ed; padding: 2px 6px; border-radius: 6px; font-size: 11.5px; }

[data-testid="stExpander"] details { border-radius: 16px !important; border: 1px solid var(--line) !important; background: #fff; }

@media (max-width: 640px) {
  .metrics, .mini-steps { grid-template-columns: repeat(2, 1fr); }
  .st-key-upload_card, .st-key-action_card, .st-key-result_card { padding: 20px 18px; }
  .prog-pct { font-size: 34px; }
}
</style>
"""

# Pure-CSS icons: st.html sanitizes inline <svg>, so icons are drawn with borders instead
TICK = '<span class="tick"></span>'
CROSS = '<span class="cross"></span>'


def render(target, markup: str) -> None:
    """Render raw HTML (bypassing markdown) into st or a placeholder."""
    target.html(markup)


def fmt_int(n: int) -> str:
    return f"{n:,}"


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


# ==========================================
# CONFIG / SECRETS
# ==========================================
def secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:  # No secrets.toml present
        return default


def load_credentials() -> dict | None:
    creds = secret("gcp_service_account")
    return dict(creds) if creds else None


# ==========================================
# SESSION STATE
# ==========================================
def init_state() -> None:
    defaults = {
        "phase": "upload",       # upload | ready | running | done | error
        "file_sig": None,
        "inspection": None,
        "logs": [],
        "result": None,
        "error": None,
        "uploader_key": 0,
        "authed": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def reset_all() -> None:
    st.session_state.uploader_key += 1
    for k in ("file_sig", "inspection", "result", "error"):
        st.session_state[k] = None
    st.session_state.logs = []
    st.session_state.phase = "upload"


def start_run() -> None:
    st.session_state.logs = []
    st.session_state.result = None
    st.session_state.error = None
    st.session_state.phase = "running"


# ==========================================
# UI COMPONENTS
# ==========================================
def hero() -> None:
    render(st, """
<div class="hero fade-up">
  <span class="hero-badge">⚡ Weekly Automation</span>
  <div class="hero-title">CIF Compliance Report</div>
  <div class="hero-sub">Upload the CifExport file — the app automatically filters incomplete CIFs,
  cross-checks them against the <b>SS26 Compliance list</b> and publishes the report straight to Google Sheets.</div>
</div>""")


def stepper(phase: str) -> None:
    index = {"upload": 0, "ready": 0, "running": 1, "error": 1, "done": 2}[phase]
    done_upload = phase in ("ready", "running", "error", "done")
    labels = ["Upload", "Process", "Done"]
    parts = []
    for i, label in enumerate(labels):
        is_done = (i == 0 and done_upload) or i < index or (i == 2 and phase == "done")
        cls = "done" if is_done else ("active" if i == index else "")
        dot = TICK if is_done else str(i + 1)
        parts.append(f'<div class="step {cls}"><div class="step-dot">{dot}</div><div class="step-label">{label}</div></div>')
        if i < len(labels) - 1:
            line_done = i < index or (i == 1 and phase == "done")
            parts.append(f'<div class="step-line {"done" if line_done else ""}"></div>')
    render(st, f'<div class="stepper fade-up">{"".join(parts)}</div>')


def console_html(logs: list[tuple[str, str, str]], live: bool, animate_last: bool = True, limit: int = 400,
                 age: float = 0.0) -> str:
    """`age` = seconds since the console first appeared; a negative animation-delay lets
    the fade-in continue (instead of restarting) when the console is re-rendered."""
    shown = logs[-limit:]
    lines = []
    for i, (ts, level, msg) in enumerate(shown):
        is_last = i == len(shown) - 1
        cls = f"ln {level}"
        if is_last and animate_last:
            cls += " new"
        if is_last and live:
            cls += " cursor"
        lines.append(f'<div class="{cls}"><span class="ts">{ts}</span>{html.escape(msg)}</div>')
    if not lines:
        lines.append('<div class="ln cursor"><span class="ts">--:--:--</span>Starting...</div>')
    badge = '<span class="live">LIVE</span>' if live else ""
    return (
        f'<div class="console" style="animation-delay:-{age:.2f}s"><div class="console-bar">'
        '<span class="dot r"></span><span class="dot y"></span>'
        f'<span class="dot g"></span><span class="console-title">cif-pipeline — processing log</span>{badge}</div>'
        f'<div class="console-body"><div>{"".join(lines)}</div></div></div>'
    )


class LiveReporter:
    """Receives pipeline events and updates the UI in real time."""

    THROTTLE = 0.12

    def __init__(self) -> None:
        self.ph_progress = st.empty()
        self.ph_console = st.empty()
        self.started = time.perf_counter()
        self.percent = 0.0
        self.shown_percent = 0.0
        self.detail = ""
        self.flip = False
        self.last_render = 0.0
        self.status = {key: "pending" for key, *_ in cp.STAGES}
        self.timing: dict[str, list[float]] = {}
        self.current = cp.STAGES[0][0]
        self.state = "running"   # running | done | error
        self._render_progress(force=True)
        self._render_console()

    # ---- Reporter protocol ----
    def log(self, message: str, level: str = "info") -> None:
        st.session_state.logs.append((datetime.now(cp.TIMEZONE).strftime("%H:%M:%S"), level, message))
        self._render_console()

    def progress(self, percent: float, detail: str = "") -> None:
        self.percent = max(self.percent, percent)
        if detail:
            self.detail = detail
        self._render_progress()

    def stage(self, key: str, status: str) -> None:
        now = time.perf_counter()
        self.status[key] = status
        if status == "running":
            self.current = key
            self.detail = ""
            self.timing[key] = [now, now]
        else:
            self.timing.setdefault(key, [now, now])[1] = now
        if status == "error":
            self.state = "error"
        self._render_progress(force=True)

    # ---- Public ----
    def finish(self, ok: bool) -> None:
        self.state = "done" if ok else "error"
        if ok:
            self.percent = 100
        self._render_progress(force=True)
        self._render_console(live=False)

    # ---- Rendering ----
    def _render_console(self, live: bool = True) -> None:
        render(self.ph_console, console_html(st.session_state.logs, live=live and self.state == "running",
                                             age=time.perf_counter() - self.started))

    def _render_progress(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.last_render < self.THROTTLE:
            return
        self.last_render = now
        self.flip = not self.flip

        label = dict((k, l) for k, l, *_ in cp.STAGES)[self.current]
        if self.state == "done":
            eyebrow, eyebrow_cls, label, fill_cls = "Completed", "ok", "Report is ready", "ok"
        elif self.state == "error":
            eyebrow, eyebrow_cls, fill_cls = "Stopped due to an error", "err", "err"
        else:
            eyebrow, eyebrow_cls, fill_cls = "Processing", "", ""

        stages_html = []
        for key, name, *_ in cp.STAGES:
            status = self.status[key]
            icon = TICK if status == "done" else (CROSS if status == "error" else "")
            meta, ic_style = "", ""
            if key in self.timing and status in ("done", "error"):
                t0, t1 = self.timing[key]
                meta = f"{t1 - t0:.1f}s"
                ic_style = f' style="animation-delay:-{now - t1:.2f}s"'  # pop once, don't replay
            elif status == "running":
                meta = self.detail or "running…"
            stages_html.append(
                f'<div class="stage {status}"><span class="ic"{ic_style}>{icon}</span><span>{name}</span>'
                f'<span class="meta">{html.escape(meta)}</span></div>'
            )

        pct = min(self.percent, 100.0)
        anim = "growA" if self.flip else "growB"
        markup = f"""
<div class="prog-card" style="animation-delay:-{now - self.started:.2f}s">
  <div class="prog-head">
    <div><div class="prog-eyebrow {eyebrow_cls}">{eyebrow}</div><div class="prog-stage">{html.escape(label)}</div></div>
    <div class="prog-pct">{int(pct)}<span>%</span></div>
  </div>
  <div class="bar"><div class="fill {fill_cls}" style="--from:{self.shown_percent:.2f}%;--to:{pct:.2f}%;animation-name:{anim}"></div></div>
  <div class="prog-foot"><span>{html.escape(self.detail)}</span><span>⏱ {fmt_duration(now - self.started)}</span></div>
  <div class="stages">{"".join(stages_html)}</div>
</div>"""
        render(self.ph_progress, markup)
        self.shown_percent = pct


# ==========================================
# SCREENS
# ==========================================
def login_gate() -> None:
    password = secret("app_password")
    if not password or st.session_state.authed:
        return
    with st.container(key="login_card"):
        render(st, '<div class="card-title">🔒 Sign in</div><div class="card-sub">Enter the internal password to use this tool.</div>')
        with st.form("login", border=False):
            value = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
            if st.form_submit_button("Continue", type="primary", width="stretch"):
                if hmac.compare_digest(value, str(password)):
                    st.session_state.authed = True
                    st.rerun()
                st.error("Incorrect password.")
    st.stop()


def missing_secrets_screen() -> None:
    with st.container(key="upload_card"):
        render(st, """
<div class="card-title">⚙️ Google Service Account is not configured</div>
<div class="card-sub">The app needs service account credentials to write to Google Sheets.</div>""")
        st.markdown(
            "Add a `[gcp_service_account]` section to the app's **Secrets** on Streamlit Cloud "
            "(*App settings → Secrets*) or to `.streamlit/secrets.toml` when running locally. "
            "See the template in `.streamlit/secrets.toml.example`."
        )
    st.stop()


def upload_section(phase: str) -> bytes | None:
    with st.container(key="upload_card"):
        render(st, '<div class="card-title">Upload CifExport file</div>'
                   '<div class="card-sub">.csv format · large files supported (~900k rows).</div>')
        uploaded = st.file_uploader(
            "File CifExport (.csv)",
            type=["csv"],
            key=f"uploader_{st.session_state.uploader_key}",
            label_visibility="collapsed",
            disabled=phase == "running",
        )

        if uploaded is None:
            # User removed the file -> back to the upload step (keep the key so swapping files doesn't wipe the uploader)
            if phase in ("ready", "error"):
                st.session_state.phase = "upload"
                st.session_state.file_sig = None
                st.session_state.inspection = None
            return None

        data = uploaded.getvalue()
        sig = (uploaded.name, uploaded.size, getattr(uploaded, "file_id", None))
        # Always reserve this slot so element positions stay stable across reruns
        # (otherwise a stale copy of the file card lingers while the pipeline runs)
        bar_slot = st.empty()
        if st.session_state.file_sig != sig:
            # New file -> quick inspection (header + line count only, no full parse)
            bar = bar_slot.progress(0, text="Reading file…")
            try:
                bar.progress(35, text="Validating column structure…")
                inspection = cp.inspect_csv(data)
                bar.progress(80, text="Estimating row count…")
                time.sleep(0.15)
                bar.progress(100, text="Validation complete")
                time.sleep(0.25)
            except Exception as exc:
                bar.empty()
                st.error(f"Could not read the CSV file: {exc}")
                return None
            bar.empty()
            st.session_state.file_sig = sig
            st.session_state.inspection = inspection
            st.session_state.result = None
            st.session_state.error = None
            st.session_state.logs = []
            if phase in ("upload", "done", "error"):
                st.session_state.phase = phase = "ready"

        ins: cp.CsvInspection = st.session_state.inspection
        chips = [
            f'<span class="chip ok">✓ {len(ins.columns)} columns</span>',
            f'<span class="chip ok">✓ Key column: {html.escape(ins.id_column)}</span>',
            f'<span class="chip {"ok" if ins.has_filter_column else "bad"}">'
            f'{"✓" if ins.has_filter_column else "✕"} {html.escape(cp.FILTER_COLUMN)}</span>',
        ]
        render(st, f"""
<div class="file-card">
  <div class="file-icon">CSV</div>
  <div><div class="file-name">{html.escape(uploaded.name)}</div>
  <div class="file-meta">{ins.size_bytes / 1_048_576:,.1f} MB · ≈ {fmt_int(ins.estimated_rows)} data rows</div></div>
</div>
<div class="chips">{"".join(chips)}</div>""")
        if not ins.has_filter_column:
            st.error(f"Required column **{cp.FILTER_COLUMN}** is missing — please check the export file.")
            return None
        return data


def action_section(phase: str, spreadsheet_id: str) -> None:
    sheet_preview = f"CIF Report - {datetime.now(cp.TIMEZONE).strftime('%d-%b-%Y')}"
    with st.container(key="action_card"):
        render(st, f"""
<div class="card-title">Ready to process</div>
<div class="action-note">The app runs end-to-end automatically and writes the result to a new sheet <b>“{sheet_preview}”</b>
in the <a href="https://docs.google.com/spreadsheets/d/{spreadsheet_id}" target="_blank">target Google Spreadsheet</a>.</div>
<div class="mini-steps">
  <div class="mini-step"><b>1 · Filter</b>CIFs where “{cp.FILTER_COLUMN}” = no</div>
  <div class="mini-step"><b>2 · Match</b>against {cp.LOOKUP_SHEET_NAME} (columns Q, AD)</div>
  <div class="mini-step"><b>3 · Publish</b>the report to Google Sheets</div>
</div>""")
        st.button(
            "🚀  Process & Publish Report to Google Sheets",
            type="primary",
            width="stretch",
            on_click=start_run,
            disabled=phase == "running",
        )


def running_section(data: bytes, credentials: dict, spreadsheet_id: str) -> None:
    reporter = LiveReporter()
    try:
        result = cp.run_pipeline(
            data, credentials, reporter,
            spreadsheet_id=spreadsheet_id,
            lookup_sheet_name=secret("lookup_sheet_name", cp.LOOKUP_SHEET_NAME),
        )
    except Exception as exc:
        reporter.finish(ok=False)
        st.session_state.error = str(exc)
        st.session_state.phase = "error"
    else:
        reporter.finish(ok=True)
        st.session_state.result = result
        st.session_state.phase = "done"
        time.sleep(0.9)  # let the user see 100% before switching screens
    st.rerun()


def result_section() -> None:
    r: cp.PipelineResult = st.session_state.result
    with st.container(key="result_card"):
        render(st, f"""
<div class="result-head">
  <div class="check-wrap"><span class="tick big"></span></div>
  <div class="result-title">Report created</div>
  <div class="result-sub">Sheet <b>“{html.escape(r.sheet_name)}”</b> · completed in {r.elapsed_seconds:,.1f}s</div>
</div>
<div class="metrics">
  <div class="metric" style="animation-delay:.05s"><div class="v">{fmt_int(r.total_rows)}</div><div class="k">Rows scanned</div></div>
  <div class="metric" style="animation-delay:.1s"><div class="v">{fmt_int(r.filtered_rows)}</div><div class="k">Incomplete rows (no)</div></div>
  <div class="metric hl" style="animation-delay:.15s"><div class="v">{fmt_int(r.unique_ids)}</div><div class="k">Unique CIF codes</div></div>
  <div class="metric" style="animation-delay:.2s"><div class="v">{fmt_int(r.matched)}</div><div class="k">Matched in Compliance list</div></div>
  <div class="metric warn" style="animation-delay:.25s"><div class="v">{fmt_int(r.not_found)}</div><div class="k">Not found</div></div>
  <div class="metric" style="animation-delay:.3s"><div class="v">{r.elapsed_seconds:,.1f}s</div><div class="k">Processing time</div></div>
</div>""")
        st.link_button("Open report in Google Sheets  ↗", r.sheet_url, type="primary", width="stretch")
        col1, col2 = st.columns(2)
        report_df = pd.DataFrame(r.report_rows[1:], columns=r.report_rows[0])
        buf = io.StringIO()
        report_df.to_csv(buf, index=False)
        col1.download_button(
            "⬇  Download a copy (.csv)",
            buf.getvalue().encode("utf-8-sig"),
            file_name=f"{r.sheet_name}.csv",
            mime="text/csv",
            width="stretch",
        )
        col2.button("↻  Process a new file", on_click=reset_all, width="stretch")

    with st.expander(f"Report preview · {fmt_int(len(report_df))} rows"):
        st.dataframe(report_df, width="stretch", hide_index=True, height=360)
    with st.expander("Processing log"):
        render(st, console_html(st.session_state.logs, live=False, animate_last=False))


def error_section() -> None:
    with st.container(key="result_card"):
        render(st, f"""
<div class="result-head">
  <div class="check-wrap err"><span class="cross big"></span></div>
  <div class="result-title">Processing did not complete</div>
  <div class="result-sub">Check the log below to see which step failed, then try again.</div>
</div>
<div class="err-box">{html.escape(st.session_state.error or "Unknown error")}</div>""")
        col1, col2 = st.columns(2)
        col1.button("↻  Try again", type="primary", on_click=start_run, width="stretch")
        col2.button("Choose another file", on_click=reset_all, width="stretch")
    render(st, console_html(st.session_state.logs, live=False, animate_last=False))


def footer(credentials: dict, spreadsheet_id: str) -> None:
    render(st, f"""
<div class="foot">
  Service account <code>{html.escape(credentials.get("client_email", ""))}</code><br/>
  Target spreadsheet · <a href="https://docs.google.com/spreadsheets/d/{spreadsheet_id}" target="_blank">open in Google Sheets ↗</a>
</div>""")


# ==========================================
# MAIN
# ==========================================
def main() -> None:
    init_state()
    render(st, CSS)
    hero()
    login_gate()

    credentials = load_credentials()
    if not credentials:
        missing_secrets_screen()
    spreadsheet_id = secret("spreadsheet_id", cp.DEFAULT_SPREADSHEET_ID)

    phase = st.session_state.phase
    # Stepper is drawn once the file state is known, but still sits above the content
    stepper_slot = st.container()

    if phase == "done" and st.session_state.result:
        with stepper_slot:
            stepper(phase)
        result_section()
    else:
        data = upload_section(phase)
        phase = st.session_state.phase
        with stepper_slot:
            stepper(phase if data is not None else "upload")
        if data is not None:
            if phase == "ready":
                action_section(phase, spreadsheet_id)
            elif phase == "running":
                running_section(data, credentials, spreadsheet_id)
            elif phase == "error":
                error_section()

    footer(credentials, spreadsheet_id)


main()
