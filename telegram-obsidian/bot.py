#!/usr/bin/env python3
"""Telegram -> Obsidian capture bot.

Self-hosted, always-on version of "Гайд 1": every message you send the bot is
appended to a single inbox file in your Obsidian vault (``inbox.md``), so the
capture works even when Obsidian is closed. No third-party plugin required.

Standard library only — no pip install needed. Voice messages are downloaded
into the vault and embedded; optional transcription is pluggable via a shell
command (off by default).

Usage:
    python3 bot.py [path/to/config.json]

Config path resolution order:
    1. CLI argument
    2. $TG_OBSIDIAN_CONFIG
    3. ./config.json  (next to this file)

Send the bot ``/start`` or ``/id`` to learn your Telegram user id so you can
lock the bot down to yourself via ``allowed_user_ids``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - very old Python
    ZoneInfo = None  # type: ignore[assignment]

API_ROOT = "https://api.telegram.org"

DEFAULT_CONFIG = {
    "bot_token": "",
    "vault_path": "",
    "inbox_file": "_BRAIN/Инбокс/inbox.md",
    "attachments_dir": "_BRAIN/Инбокс/attachments",
    "allowed_user_ids": [],
    "timezone": "",
    "template": "## {datetime} · telegram\n{content}{voice_transcript}\n\n---\n",
    "datetime_format": "%Y-%m-%d %H:%M",
    "confirm_receipt": True,
    "voice": {
        "save": True,
        "transcribe": False,
        # Shell command; "{file}" is replaced by the audio path, transcript read
        # from stdout. Example: "whisper {file} --model small --output_format txt"
        "transcribe_cmd": "",
    },
    "state_file": "state.json",
    "poll_timeout": 30,
}


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
def deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def resolve_config_path(argv: list) -> str:
    if len(argv) > 1:
        return argv[1]
    env = os.environ.get("TG_OBSIDIAN_CONFIG")
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        sys.exit(
            f"Config not found: {path}\n"
            "Copy config.example.json to config.json and fill in bot_token and vault_path."
        )
    with open(path, "r", encoding="utf-8") as f:
        user_cfg = json.load(f)
    cfg = deep_merge(DEFAULT_CONFIG, user_cfg)
    # Env overrides for the two secrets/paths so they don't need to live on disk.
    cfg["bot_token"] = os.environ.get("TG_BOT_TOKEN", cfg["bot_token"])
    cfg["vault_path"] = os.environ.get("OBSIDIAN_VAULT", cfg["vault_path"])
    if not cfg["bot_token"]:
        sys.exit("bot_token is empty (set it in config.json or $TG_BOT_TOKEN).")
    if not cfg["vault_path"]:
        sys.exit("vault_path is empty (set it in config.json or $OBSIDIAN_VAULT).")
    cfg["vault_path"] = os.path.expanduser(cfg["vault_path"])
    return cfg


# --------------------------------------------------------------------------- #
# Formatting / writing (pure, unit-tested offline)
# --------------------------------------------------------------------------- #
def now_dt(timezone: str) -> datetime:
    if timezone and ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(timezone))
        except Exception:  # bad tz name -> fall back to local time
            pass
    return datetime.now()


def message_dt(msg: dict, timezone: str) -> datetime:
    """Timestamp for the inbox block.

    Prefer Telegram's ``date`` (Unix UTC, the time the message was *sent*) so
    that messages delivered late — after a restart or polling delay — are filed
    under their real time rather than the moment we happened to process them.
    Falls back to the current time if ``date`` is missing.
    """
    ts = msg.get("date")
    if ts:
        if timezone and ZoneInfo is not None:
            try:
                return datetime.fromtimestamp(ts, ZoneInfo(timezone))
            except Exception:  # bad tz name -> local time
                pass
        return datetime.fromtimestamp(ts)
    return now_dt(timezone)


def format_entry(template: str, dt: datetime, datetime_format: str,
                 content: str, voice_transcript: str = "") -> str:
    """Render one inbox block from the template.

    Placeholders: {datetime}, {content}, {voice_transcript}. Values are inserted
    literally, so braces inside the message text are never re-interpreted.
    """
    return template.format(
        datetime=dt.strftime(datetime_format),
        content=content or "",
        voice_transcript=voice_transcript or "",
    )


def append_inbox(inbox_path: str, entry: str) -> None:
    os.makedirs(os.path.dirname(inbox_path) or ".", exist_ok=True)
    needs_gap = os.path.exists(inbox_path) and os.path.getsize(inbox_path) > 0
    with open(inbox_path, "a", encoding="utf-8") as f:
        if needs_gap:
            f.write("\n")
        f.write(entry if entry.endswith("\n") else entry + "\n")


# --------------------------------------------------------------------------- #
# Telegram API (stdlib HTTP)
# --------------------------------------------------------------------------- #
def api_call(token: str, method: str, params: dict | None = None,
             timeout: int = 60) -> dict:
    url = f"{API_ROOT}/bot{token}/{method}"
    data = None
    if params:
        encoded = {}
        for key, value in params.items():
            encoded[key] = value if isinstance(value, str) else json.dumps(value)
        data = urllib.parse.urlencode(encoded).encode("utf-8")
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload}")
    return payload["result"]


def get_updates(token: str, offset: int | None, poll_timeout: int) -> list:
    params: dict = {"timeout": poll_timeout, "allowed_updates": ["message"]}
    if offset is not None:
        params["offset"] = offset
    return api_call(token, "getUpdates", params, timeout=poll_timeout + 15)


def send_message(token: str, chat_id: int, text: str) -> None:
    try:
        api_call(token, "sendMessage", {"chat_id": chat_id, "text": text})
    except Exception as exc:  # confirmations are best-effort
        log(f"sendMessage failed: {exc}")


def download_file(token: str, file_id: str, dest: str) -> None:
    info = api_call(token, "getFile", {"file_id": file_id})
    file_path = info["file_path"]
    url = f"{API_ROOT}/file/bot{token}/{file_path}"
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as out:
        shutil.copyfileobj(resp, out)


# --------------------------------------------------------------------------- #
# Voice handling
# --------------------------------------------------------------------------- #
def run_transcription(cmd_template: str, audio_path: str) -> str:
    cmd = cmd_template.replace("{file}", shlex.quote(audio_path))
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=900
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "transcription command failed")
    return proc.stdout.strip()


def handle_voice(cfg: dict, msg: dict) -> str:
    """Download a voice/audio message and return the markdown to append.

    With transcription enabled, returns the transcript text. Otherwise returns
    an Obsidian embed link to the saved audio file.
    """
    media = msg.get("voice") or msg.get("audio")
    if not media:
        return ""
    voice_cfg = cfg["voice"]
    file_id = media["file_id"]
    uid = media.get("file_unique_id", file_id)
    # Telegram voice notes are .oga/.ogg; audio uploads keep their extension.
    ext = ".ogg" if msg.get("voice") else os.path.splitext(
        media.get("file_name", "audio.mp3"))[1] or ".mp3"
    filename = f"voice_{uid}{ext}"
    abs_dir = os.path.join(cfg["vault_path"], cfg["attachments_dir"])
    abs_path = os.path.join(abs_dir, filename)

    if voice_cfg.get("save", True):
        download_file(cfg["bot_token"], file_id, abs_path)

    if voice_cfg.get("transcribe") and voice_cfg.get("transcribe_cmd"):
        try:
            transcript = run_transcription(voice_cfg["transcribe_cmd"], abs_path)
            if transcript:
                return "\n" + transcript
        except Exception as exc:
            log(f"transcription failed: {exc}")
            # fall through to embed so the audio is never lost

    if voice_cfg.get("save", True):
        return f"\n![[{filename}]]"
    return "\n[voice message]"


# --------------------------------------------------------------------------- #
# Message processing
# --------------------------------------------------------------------------- #
def is_allowed(cfg: dict, msg: dict) -> bool:
    allowed = cfg.get("allowed_user_ids") or []
    if not allowed:
        return True  # open mode (logged at startup)
    sender = (msg.get("from") or {}).get("id")
    return sender in allowed


def process_message(cfg: dict, msg: dict) -> None:
    sender = msg.get("from") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    user_id = sender.get("id")

    text = msg.get("text") or ""

    # Helper commands — answer and don't write to the inbox.
    if text.strip() in ("/start", "/id"):
        send_message(
            cfg["bot_token"], chat_id,
            f"Привет! Твой Telegram user id: {user_id}\n"
            "Добавь его в allowed_user_ids в config.json, чтобы бот принимал только тебя.",
        )
        return

    if not is_allowed(cfg, msg):
        log(f"ignored message from disallowed user {user_id}")
        send_message(cfg["bot_token"], chat_id, "⛔ Этот бот привязан к другому аккаунту.")
        return

    content = text or msg.get("caption") or ""
    voice_transcript = ""
    if msg.get("voice") or msg.get("audio"):
        voice_transcript = handle_voice(cfg, msg)

    if not content and not voice_transcript:
        # Photos/documents/stickers without caption: keep a marker rather than drop.
        if any(k in msg for k in ("photo", "document", "sticker", "video")):
            content = "[вложение без текста]"
        else:
            log("skipped message with no usable content")
            return

    dt = message_dt(msg, cfg.get("timezone", ""))
    entry = format_entry(
        cfg["template"], dt, cfg["datetime_format"], content, voice_transcript
    )
    inbox_path = os.path.join(cfg["vault_path"], cfg["inbox_file"])
    append_inbox(inbox_path, entry)
    log(f"appended message {msg.get('message_id')} -> {cfg['inbox_file']}")

    if cfg.get("confirm_receipt", True):
        send_message(cfg["bot_token"], chat_id, "✓ в инбоксе")


# --------------------------------------------------------------------------- #
# State + main loop
# --------------------------------------------------------------------------- #
def state_path(cfg: dict, config_file: str) -> str:
    sf = cfg.get("state_file", "state.json")
    if os.path.isabs(sf):
        return sf
    return os.path.join(os.path.dirname(os.path.abspath(config_file)), sf)


def load_offset(path: str) -> int | None:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("offset")
        except Exception:
            return None
    return None


def save_offset(path: str, offset: int) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"offset": offset}, f)


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def main(argv: list) -> None:
    config_file = resolve_config_path(argv)
    cfg = load_config(config_file)
    sf = state_path(cfg, config_file)
    offset = load_offset(sf)

    if not cfg.get("allowed_user_ids"):
        log("WARNING: allowed_user_ids is empty — bot accepts messages from anyone. "
            "Send /id to the bot and add your id to lock it down.")
    log(f"vault: {cfg['vault_path']}")
    log(f"inbox: {cfg['inbox_file']}")
    log("polling Telegram... (Ctrl-C to stop)")

    while True:
        try:
            updates = get_updates(cfg["bot_token"], offset, cfg["poll_timeout"])
            for update in updates:
                msg = update.get("message")
                if msg:
                    try:
                        process_message(cfg, msg)
                    except Exception as exc:
                        # Capture failed (vault offline, disk full, voice download
                        # error...). Do NOT advance the offset: leave the update in
                        # Telegram's queue so it is redelivered and retried, rather
                        # than silently dropping the note. A retry may re-append a
                        # message whose write partly succeeded — duplicates are
                        # acceptable (triage dedups); lost thoughts are not.
                        log(f"error processing update {update['update_id']}: {exc} "
                            "— offset not advanced, will retry")
                        time.sleep(5)
                        break
                # Only commit progress past an update once it is safely captured.
                offset = update["update_id"] + 1
                save_offset(sf, offset)
        except KeyboardInterrupt:
            log("stopped.")
            return
        except urllib.error.URLError as exc:
            log(f"network error: {exc} — retrying in 5s "
                "(if Telegram is blocked by your ISP, use a VPN).")
            time.sleep(5)
        except Exception as exc:
            log(f"unexpected error: {exc} — retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main(sys.argv)
