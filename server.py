"""
KAM Supply Intelligence Agent — server.py
Sprint 3, US-10: Flask API wrapper

Endpoints:
  POST /ask     — accepts { "question": "...", "export_xlsx": false }
                  returns structured JSON answer
  GET  /health  — returns 200 OK with build info

n8n integration:
  n8n sends a POST /ask, reads the `answer` field from the response,
  and posts it to the configured Slack channel.

Usage (local):
  python server.py
  curl -s -X POST http://localhost:5000/ask \
       -H "Content-Type: application/json" \
       -d '{"question": "How many suppliers does Check24 have?"}'

Environment variables required (inherited from agent pipeline):
  OPENAI_API_KEY
  SF_CONSUMER_KEY / SF_CONSUMER_SECRET / SF_ORG_DOMAIN
  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY
  SERVER_API_KEY   (optional — if set, Bearer auth is enforced on /ask)
"""

import os
import logging
import traceback
from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify
from dotenv import load_dotenv

# ── Bootstrap ─────────────────────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Lazy-import the agent so import errors surface at runtime with a clear message
try:
    from agent_format_answer import run_agent
    AGENT_LOADED = True
    AGENT_LOAD_ERROR = None
except Exception as exc:  # pragma: no cover
    AGENT_LOADED = False
    AGENT_LOAD_ERROR = str(exc)
    log.error("Failed to import agent_format_answer: %s", exc)

# ── App ───────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

BUILD_TIME = datetime.now(timezone.utc).isoformat()
SERVER_API_KEY = os.getenv("SERVER_API_KEY")  # optional Bearer token guard


# ── Auth decorator ────────────────────────────────────────────────────────────

def require_api_key(f):
    """
    If SERVER_API_KEY is set in .env, every POST /ask must include:
        Authorization: Bearer <SERVER_API_KEY>
    If the env var is absent the decorator is a no-op (dev mode).
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not SERVER_API_KEY:
            return f(*args, **kwargs)
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer ") or \
                auth_header[len("Bearer "):] != SERVER_API_KEY:
            log.warning("Rejected request — invalid or missing API key")
            return jsonify({
                "ok":    False,
                "error": "Unauthorized — invalid or missing Bearer token.",
            }), 401
        return f(*args, **kwargs)
    return decorated


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cost_summary_to_dict(cs: dict | None) -> dict:
    """Return a serialisation-safe subset of the cost_summary dict."""
    if not cs:
        return {}
    return {
        "total_cost_usd":          round(cs.get("total_cost_usd", 0.0), 6),
        "total_prompt_tokens":     cs.get("total_prompt_tokens", 0),
        "total_completion_tokens": cs.get("total_completion_tokens", 0),
        "total_supabase_queries":  cs.get("total_supabase_queries", 0),
        "supabase_tier":           cs.get("supabase_tier", "free"),
    }


def _build_error_response(message: str, http_status: int = 500) -> tuple:
    payload = {
        "ok":        False,
        "error":     message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload), http_status


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """
    GET /health
    Returns 200 with build metadata.
    Used by n8n to verify the Flask server is reachable before sending questions.
    """
    return jsonify({
        "ok":          True,
        "status":      "healthy",
        "agent_ready": AGENT_LOADED,
        "build_time":  BUILD_TIME,
        "version":     "sprint3-us13",
    }), 200


@app.post("/ask")
@require_api_key
def ask():
    """
    POST /ask
    Body (JSON):
      {
        "question":     "How many suppliers does Check24 have?",   ← required
        "export_xlsx":  false                                       ← optional
      }

    Response (JSON):
      {
        "ok":          true,
        "answer":      "┌─ CLIENT PROFILE ...",   ← formatted text block
        "client_name": "Check24",
        "question_type": "supplier_count",
        "xlsx_path":   null,
        "cost":        { ... },
        "timestamp":   "2025-05-21T09:00:00+00:00"
      }

    n8n reads the `answer` field and posts it verbatim to Slack.
    """
    # ── Guard: agent must be importable ───────────────────────────────────────
    if not AGENT_LOADED:
        log.error("Agent not loaded — cannot serve /ask")
        return _build_error_response(
            f"Agent failed to load: {AGENT_LOAD_ERROR}", 503
        )

    # ── Parse body ────────────────────────────────────────────────────────────
    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()

    if not question:
        return _build_error_response(
            "Missing required field: 'question' must be a non-empty string.", 400
        )

    export_xlsx = bool(body.get("export_xlsx", False))

    log.info("POST /ask  question=%r  export_xlsx=%s", question, export_xlsx)

    # ── Run agent ─────────────────────────────────────────────────────────────
    try:
        result = run_agent(question, export_csv=export_xlsx)
    except Exception as exc:  # pragma: no cover
        log.error("Agent raised an exception:\n%s", traceback.format_exc())
        return _build_error_response(
            "An internal error occurred while processing your question. "
            "Please try again or contact support.",
            500,
        )

    # ── Build response ────────────────────────────────────────────────────────
    answer = result.get("final_answer") or (
        "I couldn't generate an answer for that question. "
        "Supported clients: Check24, Autoslash, HappyCar."
    )

    payload = {
        "ok":            True,
        "answer":        answer,
        "client_name":   result.get("client_name"),
        "question_type": result.get("question_type"),
        "xlsx_path":     result.get("csv_path"),   # None when not exported
        "cost":          _cost_summary_to_dict(result.get("cost_summary")),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }

    log.info(
        "POST /ask  client=%s  type=%s  cost=$%.6f",
        payload["client_name"],
        payload["question_type"],
        payload["cost"].get("total_cost_usd", 0.0),
    )
    return jsonify(payload), 200


@app.post("/upload-to-slack")
def upload_to_slack():
    """
    POST /upload-to-slack
    Body (JSON):
      {
        "xlsx_path":     "./exports/Check24_supplier_list_2026-05-21.xlsx",
        "client_name":   "Check24",
        "question_type": "supplier_list",
        "channel_id":    "C0B53G3PE6Q",
        "thread_ts":     "1779354180.528469"
      }

    Implements Slack's 3-step file upload API (post-deprecation):
      1. files.getUploadURLExternal  → upload_url + file_id
      2. POST raw bytes to upload_url
      3. files.completeUploadExternal → published in channel/thread
    """
    import os as _os
    import requests as _requests

    SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN", "xoxb-11154311307111-11167834849814-Uq9Lk6vFSHBYb3QDQfDJBiLi")

    body        = request.get_json(silent=True) or {}
    xlsx_path   = (body.get("xlsx_path") or "").strip()
    client_name = body.get("client_name", "Unknown")
    q_type      = body.get("question_type", "query")
    channel_id  = body.get("channel_id", "")
    thread_ts   = body.get("thread_ts", "")

    if not xlsx_path:
        return _build_error_response("Missing xlsx_path.", 400)

    # Jail to exports dir
    export_dir = _os.path.realpath("./exports")
    safe_path  = _os.path.realpath(_os.path.join(export_dir, _os.path.basename(xlsx_path)))
    if not safe_path.startswith(export_dir) or not _os.path.isfile(safe_path):
        return _build_error_response("File not found.", 404)

    file_name = _os.path.basename(safe_path)
    file_size = _os.path.getsize(safe_path)

    headers_auth = {"Authorization": f"Bearer {SLACK_TOKEN}"}

    # Step 1 — get upload URL
    r1 = _requests.post(
        "https://slack.com/api/files.getUploadURLExternal",
        headers=headers_auth,
        data={"filename": file_name, "length": file_size},
        timeout=10,
    )
    d1 = r1.json()
    if not d1.get("ok"):
        log.error("getUploadURLExternal failed: %s", d1)
        return _build_error_response(f"Slack upload step 1 failed: {d1.get('error')}", 502)

    upload_url = d1["upload_url"]
    file_id    = d1["file_id"]

    # Step 2 — upload raw bytes
    with open(safe_path, "rb") as fh:
        r2 = _requests.post(
            upload_url,
            headers={"Content-Type": "application/octet-stream"},
            data=fh,
            timeout=30,
        )
    if r2.status_code != 200:
        log.error("Binary upload failed: %s %s", r2.status_code, r2.text[:200])
        return _build_error_response("Slack upload step 2 failed.", 502)

    # Step 3 — complete and publish
    payload = {
        "files":           [{"id": file_id, "title": file_name}],
        "channel_id":      channel_id,
        "initial_comment": f"📎 Excel export — {client_name} · {q_type}",
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    r3 = _requests.post(
        "https://slack.com/api/files.completeUploadExternal",
        headers={**headers_auth, "Content-Type": "application/json"},
        json=payload,
        timeout=10,
    )
    d3 = r3.json()
    if not d3.get("ok"):
        log.error("completeUploadExternal failed: %s", d3)
        return _build_error_response(f"Slack upload step 3 failed: {d3.get('error')}", 502)

    log.info("upload-to-slack  file=%s  channel=%s  file_id=%s", file_name, channel_id, file_id)
    return jsonify({"ok": True, "file_id": file_id, "file_name": file_name}), 200


@app.get("/download")
def download():
    """
    GET /download?path=./exports/Check24_product_details_2025-05-21.xlsx

    Serves the XLSX file produced by the agent as a binary attachment.
    n8n calls this endpoint after /ask returns a non-null xlsx_path, then
    uploads the binary to Slack using the Slack — Upload File node.

    Security: only files inside EXPORT_DIR are served; any path traversal
    attempt outside that folder is rejected with 400.
    """
    import os as _os
    from flask import send_file

    raw_path = request.args.get("path", "").strip()
    if not raw_path:
        return _build_error_response("Missing required query param: 'path'.", 400)

    # Resolve and jail to EXPORT_DIR so callers can't walk the filesystem
    export_dir = _os.path.realpath("./exports")
    safe_path  = _os.path.realpath(
        _os.path.join(export_dir, _os.path.basename(raw_path))
    )
    if not safe_path.startswith(export_dir):
        return _build_error_response("Invalid path.", 400)

    if not _os.path.isfile(safe_path):
        log.warning("GET /download — file not found: %s", safe_path)
        return _build_error_response(f"File not found: {_os.path.basename(raw_path)}", 404)

    log.info("GET /download  file=%s", safe_path)
    return send_file(
        safe_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=_os.path.basename(safe_path),
    )


# ── 404 / 405 handlers ────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(_):
    return jsonify({"ok": False, "error": "Endpoint not found."}), 404


@app.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"ok": False, "error": "Method not allowed."}), 405


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    log.info("Starting KAM Supply Intelligence server on %s:%s", host, port)
    log.info("Agent loaded: %s", AGENT_LOADED)
    if SERVER_API_KEY:
        log.info("Bearer auth: ENABLED")
    else:
        log.info("Bearer auth: DISABLED (set SERVER_API_KEY in .env to enable)")

    app.run(host=host, port=port, debug=debug)
