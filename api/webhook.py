"""
Telegram bot webhook for Vercel (Python serverless function).

Route:  POST /api/webhook   <- Telegram delivers updates here
        GET  /api/webhook   <- simple health check

Environment variables (set in Vercel, never in code):
    TELEGRAM_BOT_TOKEN       token from @BotFather
    TELEGRAM_WEBHOOK_SECRET  random string, also passed to setWebhook as secret_token

This file is organised in clearly separated sections:
    1. Configuration
    2. Telegram API client
    3. AI integration hook (optional, disabled by default)
    4. Reply logic (pure functions, no network)
    5. Update processing
    6. HTTP handler (Vercel entry point)
"""

import hmac
import html
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler

import requests

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-bot")

TELEGRAM_API = "https://api.telegram.org"
REQUEST_TIMEOUT = 8            # seconds; keeps us well inside the function limit
MAX_BODY_BYTES = 1_000_000     # reject absurdly large request bodies
MAX_MESSAGE_LEN = 4096         # Telegram's per-message text limit
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def get_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def get_secret() -> str:
    return os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()


# ---------------------------------------------------------------------------
# 2. Telegram API client
# ---------------------------------------------------------------------------

def telegram_call(method: str, payload: dict):
    """
    Call a Telegram Bot API method. Returns the parsed JSON dict on success,
    or None on any failure. Never logs the URL, because it contains the token.
    """
    token = get_token()
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set")
        return None

    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        # Only the exception class name is logged: messages can embed the URL.
        logger.error("Telegram %s failed: %s", method, type(exc).__name__)
        return None

    if not data.get("ok"):
        logger.error(
            "Telegram %s returned error %s: %s",
            method, data.get("error_code"), data.get("description"),
        )
        return None
    return data


def send_message(chat_id, text: str):
    """Send an HTML-formatted text message. `text` must already be HTML-safe."""
    return telegram_call(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text[:MAX_MESSAGE_LEN],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )


# ---------------------------------------------------------------------------
# 3. AI integration hook (optional, disabled by default)
# ---------------------------------------------------------------------------

def ai_reply(text: str, user: dict):
    """
    Return an AI-generated answer for `text`, or None to use the built-in
    fallback. Currently NO AI model is connected, so this always returns None
    and the bot does not answer arbitrary questions.

    To add AI later, implement it here only (webhook handling stays untouched):
      1. Add the provider's SDK or call its HTTP API with `requests`.
      2. Store the API key as a Vercel environment variable (e.g. AI_API_KEY).
      3. Keep the call under ~8 seconds and return plain text (it is escaped
         for you), or return None on any failure.
    AI providers generally bill per request/token; see the README.
    """
    return None


# ---------------------------------------------------------------------------
# 4. Reply logic (pure functions)
# ---------------------------------------------------------------------------

GREETINGS = {
    "hi", "hii", "hiii", "hello", "hey", "heyy", "hola", "namaste", "namaskaram",
    "good morning", "good afternoon", "good evening", "good night", "yo", "sup",
}
THANKS = {"thanks", "thank you", "thx", "ty", "thanks a lot", "thank you so much"}
GOODBYES = {"bye", "goodbye", "see you", "see ya", "cya", "good bye"}
HOW_ARE_YOU = {"how are you", "how are you doing", "hows it going", "how r u", "whats up"}
WHO_ARE_YOU = {"who are you", "what are you", "who is this", "what is your name", "whats your name"}
WHAT_CAN_YOU_DO = {"what can you do", "what do you do", "how do you work", "how does this work"}
HELP_WORDS = {"help", "menu", "commands"}


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    cleaned = re.sub(r"[^\w\s]", "", text.lower().replace("'", ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def display_name(first_name) -> str:
    """HTML-safe first name, or a friendly default."""
    if isinstance(first_name, str) and first_name.strip():
        return html.escape(first_name.strip()[:64])
    return "there"


def welcome_text(first_name) -> str:
    return (
        f"👋 Hello, <b>{display_name(first_name)}</b>! Welcome.\n\n"
        "I'm an automatic reply bot. Just send me a message and I'll respond right away.\n\n"
        "<b>How to use me</b>\n"
        "• Send any text message\n"
        "• /help – see what I can do\n"
        "• /about – learn about this bot"
    )


def help_text() -> str:
    return (
        "<b>Available commands</b>\n"
        "/start – show the welcome message\n"
        "/help – show this help\n"
        "/about – about this bot\n\n"
        "You can also say hello or ask what I can do. "
        "I only understand a limited set of messages for now."
    )


def about_text() -> str:
    return (
        "<b>About this bot</b>\n"
        "I'm an automatic reply bot running as a serverless function on Vercel. "
        "I answer greetings and a few common questions with prepared replies. "
        "I am not an AI assistant and can't answer arbitrary questions."
    )


UNKNOWN_TEXT = (
    "Sorry, I didn't understand that. 🤔\n"
    "I only know a few things right now. Try /help to see what I can do."
)
NON_TEXT_TEXT = "I can only read text messages for now. Please send me some text, or try /help."


def parse_command(text: str):
    """
    '/start', '/help@MyBot', '/about now' -> ('start' | 'help' | 'about', args).
    Returns (None, '') when `text` is not a command.
    """
    if not text.startswith("/"):
        return None, ""
    head, _, args = text.partition(" ")
    command = head[1:].split("@", 1)[0].lower()
    return command, args.strip()


def build_reply(text: str, user: dict) -> str:
    """Return the HTML-safe reply for a text message."""
    first_name = user.get("first_name")

    command, _ = parse_command(text.strip())
    if command == "start":
        return welcome_text(first_name)
    if command == "help":
        return help_text()
    if command == "about":
        return about_text()
    if command is not None:
        return UNKNOWN_TEXT

    phrase = normalize(text)
    if phrase in GREETINGS:
        return f"Hello, <b>{display_name(first_name)}</b>! 👋 How can I help? Try /help."
    if phrase in HOW_ARE_YOU:
        return "I'm running fine, thanks for asking! 😊 Try /help to see what I can do."
    if phrase in WHO_ARE_YOU:
        return about_text()
    if phrase in WHAT_CAN_YOU_DO or phrase in HELP_WORDS:
        return help_text()
    if phrase in THANKS:
        return "You're welcome! 😊"
    if phrase in GOODBYES:
        return "Goodbye! 👋 Send /start any time to chat again."

    # Optional AI fallback (returns None until an AI model is connected).
    try:
        ai_text = ai_reply(text, user)
    except Exception as exc:  # never let the AI layer break the webhook
        logger.error("ai_reply failed: %s", type(exc).__name__)
        ai_text = None
    if isinstance(ai_text, str) and ai_text.strip():
        return html.escape(ai_text.strip())

    return UNKNOWN_TEXT


# ---------------------------------------------------------------------------
# 5. Update processing
# ---------------------------------------------------------------------------

def process_update(update: dict) -> None:
    """Handle one Telegram update. Only plain 'message' updates are answered."""
    message = update.get("message")
    if not isinstance(message, dict):
        return  # edited messages, callbacks, etc. are ignored

    chat = message.get("chat")
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    if chat_id is None:
        return

    sender = message.get("from")
    sender = sender if isinstance(sender, dict) else {}
    if sender.get("is_bot"):
        return  # never reply to other bots (avoids loops)

    text = message.get("text")
    if isinstance(text, str) and text.strip():
        send_message(chat_id, build_reply(text, sender))
    else:
        send_message(chat_id, NON_TEXT_TEXT)


# ---------------------------------------------------------------------------
# 6. HTTP handler (Vercel entry point)
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    """Vercel's Python runtime looks for a class named `handler` in this file."""

    def _respond(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        # Health check only; reveals nothing about configuration.
        self._respond(200, {"status": "ok"})

    def do_POST(self):
        token, secret = get_token(), get_secret()
        if not token or not secret:
            logger.error("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_WEBHOOK_SECRET")
            self._respond(500, {"ok": False, "error": "server not configured"})
            return

        # 1) Authenticate: Telegram echoes the secret_token given to setWebhook.
        provided = self.headers.get(SECRET_HEADER, "")
        if not hmac.compare_digest(provided.encode("utf-8"), secret.encode("utf-8")):
            self._respond(403, {"ok": False, "error": "forbidden"})
            return

        # 2) Read and validate the body.
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, {"ok": False, "error": "bad content-length"})
            return
        if length <= 0:
            self._respond(400, {"ok": False, "error": "empty body"})
            return
        if length > MAX_BODY_BYTES:
            self._respond(413, {"ok": False, "error": "body too large"})
            return

        try:
            update = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            self._respond(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(update, dict):
            self._respond(400, {"ok": False, "error": "invalid update"})
            return

        # 3) Process. Always answer 200 once authenticated and parsed, even if
        #    sending the reply failed, so Telegram doesn't retry the same update.
        try:
            process_update(update)
        except Exception as exc:
            logger.error("process_update failed: %s", type(exc).__name__)
        self._respond(200, {"ok": True})
