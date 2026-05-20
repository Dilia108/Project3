"""
KAM Supply Intelligence Agent — slack_bot.py
Sprint 3, US-10: Slack integration via Socket Mode

Replaces the n8n webhook approach with a direct Slack Bolt connection.
Socket Mode requires no public URL — works on localhost.

Required .env variables:
  SLACK_BOT_TOKEN   = xoxb-...   (Bot User OAuth Token)
  SLACK_APP_TOKEN   = xapp-...   (App-Level Token with connections:write scope)

Usage:
  python slack_bot.py

The bot will:
  - Listen for messages in any channel it's invited to
  - Ignore messages from bots (prevents infinite loops)
  - Call run_agent() with the message text
  - Post the answer as a thread reply
"""

import os
import logging
from dotenv import load_dotenv

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from agent_format_answer import run_agent

# ── Bootstrap ─────────────────────────────────────────────────────────────────

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Slack App ─────────────────────────────────────────────────────────────────

app = App(token=os.getenv("SLACK_BOT_TOKEN"))


# ── Message handler ───────────────────────────────────────────────────────────

@app.event("message")
def handle_message(event, say, logger):
    """
    Fires on every message in channels the bot is in.
    Ignores bot messages to prevent infinite loops.
    """
    # Ignore bot messages (including our own replies)
    if event.get("bot_id") or event.get("subtype"):
        return

    question = event.get("text", "").strip()
    thread_ts = event.get("thread_ts") or event.get("ts")
    channel   = event.get("channel")

    if not question:
        return

    log.info("Message received — channel=%s question=%r", channel, question)

    # ── Typing indicator (optional, shows the bot is working) ─────────────────
    try:
        app.client.reactions_add(
            channel=channel,
            timestamp=event.get("ts"),
            name="hourglass_flowing_sand",
        )
    except Exception:
        pass  # Reaction is cosmetic — don't fail if it errors

    # ── Run agent ─────────────────────────────────────────────────────────────
    try:
        result  = run_agent(question, export_csv=False)
        answer  = result.get("final_answer") or (
            "I couldn't generate an answer. "
            "Supported clients: Check24, Autoslash, HappyCar."
        )
        log.info(
            "Agent response — client=%s type=%s",
            result.get("client_name"),
            result.get("question_type"),
        )
    except Exception as exc:
        log.error("Agent error: %s", exc)
        answer = (
            ":warning: An internal error occurred while processing your question.\n"
            "Please try again or check the server logs."
        )

    # ── Post answer as thread reply ───────────────────────────────────────────
    say(text=answer, thread_ts=thread_ts)

    # ── Remove hourglass reaction ─────────────────────────────────────────────
    try:
        app.client.reactions_remove(
            channel=channel,
            timestamp=event.get("ts"),
            name="hourglass_flowing_sand",
        )
    except Exception:
        pass


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    app_token = os.getenv("SLACK_APP_TOKEN")

    if not bot_token:
        raise ValueError("SLACK_BOT_TOKEN is not set in .env")
    if not app_token:
        raise ValueError("SLACK_APP_TOKEN is not set in .env")
    if not app_token.startswith("xapp-"):
        raise ValueError("SLACK_APP_TOKEN must start with xapp- (App-Level Token)")

    log.info("Starting KAM Slack bot (Socket Mode)...")
    log.info("Bot token: %s...%s", bot_token[:12], bot_token[-4:])

    handler = SocketModeHandler(app, app_token)
    handler.start()
