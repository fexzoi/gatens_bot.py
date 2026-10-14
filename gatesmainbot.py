"""Gates Official Bot — GTS - GATES NETWORK.

BOT_TOKEN has a fallback value; preferably set BOT_TOKEN in Railway Variables. Optional: OWNER_ID, PORT, DATABASE_FILE.
Requires: aiogram>=3.0.0 and aiohttp.
"""
import asyncio
import hashlib
import html
import json
import logging
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

BOT_TOKEN = os.getenv("BOT_TOKEN", "8841797167:AAEixfNdHXIbe2yjwbQX3-Ba9fYr5zq-5cU").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8480522053"))
DB_FILE = Path(os.getenv("DATABASE_FILE", "gatens_database.json"))
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it in Railway -> Variables.")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("gates-official-bot")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def default_db() -> dict[str, Any]:
    return {
        "users": {},
        "channels": {},
        "moderators": {},
        "pending_moderators": {},
        "pending_verifications": {},
        "reports": {},
        "blacklist": {},
        "published_posts": {},
        "settings": {"network_name": "GTS - GATES NETWORK"},
    }


def load_db() -> dict[str, Any]:
    if not DB_FILE.exists():
        return default_db()
    try:
        value = json.loads(DB_FILE.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return default_db()
        defaults = default_db()
        for key, default in defaults.items():
            if key not in value or not isinstance(value[key], type(default)):
                value[key] = default
        return value
    except (OSError, json.JSONDecodeError):
        log.exception("Could not load database; using an empty database")
        return default_db()


DB = load_db()


def save_db() -> None:
    tmp = None
    try:
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=DB_FILE.name, suffix=".tmp", dir=str(DB_FILE.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(DB, file, ensure_ascii=False, indent=2)
        os.replace(tmp, DB_FILE)
    except OSError:
        log.exception("Could not save database")
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def is_moderator(user_id: int) -> bool:
    return bool(DB["moderators"].get(str(user_id), {}).get("approved"))


def can_manage(user_id: int) -> bool:
    return is_owner(user_id) or is_moderator(user_id)


def register_user(user) -> None:
    key = str(user.id)
    row = DB["users"].setdefault(
        key,
        {"id": user.id, "username": "", "name": "", "joined_at": now_iso(), "verified": False},
    )
    row["username"] = user.username or ""
    row["name"] = user.full_name or ""
    save_db()


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Connect Channel"), KeyboardButton(text="📝 Create Post")],
            [KeyboardButton(text="✅ Verification"), KeyboardButton(text="🪪 My ID")],
            [KeyboardButton(text="🌐 Network"), KeyboardButton(text="❓ Help")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Choose an option",
    )


class ConnectState(StatesGroup):
    channel = State()


class PostState(StatesGroup):
    channel = State()
    content = State()
    buttons = State()
    confirm = State()


class VerifyState(StatesGroup):
    details = State()


class LoginState(StatesGroup):
    password = State()


class BroadcastState(StatesGroup):
    text = State()
    confirm = State()


class EditPostState(StatesGroup):
    channel = State()
    message_id = State()
    content = State()
    buttons = State()


class ReportState(StatesGroup):
    target = State()
    reason = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


def admin_keyboard():
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Pending moderators", callback_data="owner:mods"))
    kb.row(InlineKeyboardButton(text="Pending verifications", callback_data="owner:verify"))
    kb.row(InlineKeyboardButton(text="Broadcast", callback_data="owner:broadcast"))
    kb.row(InlineKeyboardButton(text="Statistics", callback_data="owner:stats"))
    return kb.as_markup()


async def health_server():
    async def health(_request):
        return web.Response(text="Gates Official Bot is running")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    log.info("Health server listening on %s", PORT)
    return runner


async def check_channel(channel_ref: str, user_id: int | None = None):
    try:
        chat = await bot.get_chat(channel_ref)
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(chat.id, me.id)
        if bot_member.status not in {"administrator", "creator"}:
            return False, None, "Please make this bot an administrator in that channel first."
        if user_id is not None:
            user_member = await bot.get_chat_member(chat.id, user_id)
            if user_member.status not in {"administrator", "creator"}:
                return False, None, "You must be a channel administrator to connect it."
        return True, chat, ""
    except TelegramAPIError:
        return False, None, (
            "I couldn't access that channel. Check the @username or numeric channel ID, "
            "and ensure the bot is already a channel administrator."
        )


async def show_home(message: Message):
    name = esc(message.from_user.full_name if message.from_user else "there")
    await message.answer(
        f"<b>Gates Official Bot</b>\n<i>GTS - GATES NETWORK</i>\n\n"
        f"Welcome, {name}.\nChoose an option below.",
        reply_markup=main_menu(),
    )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user:
        register_user(message.from_user)
    await show_home(message)


@dp.message(Command("help"))
@dp.message(F.text == "❓ Help")
async def help_command(message: Message):
    await message.answer(
        "<b>Gates Official Bot — Help</b>\n\n"
        "• <b>Connect Channel:</b> connect a channel you administer; the bot must also be an admin.\n"
        "• <b>Create Post:</b> prepare text, photo, or video posts and publish to a connected channel.\n"
        "• <b>Verification:</b> submit a request for owner review.\n"
        "• <b>My ID:</b> show your Telegram ID.\n"
        "• <b>Moderator:</b> use /login after the owner creates your password.\n\n"
        "• /status [user_id] — check verification status.\n"
        "• /report [user_id] — report a user with a reason.\n"
        "• /editpost — edit a published bot post.\n"
        "• /report — submit a report for owner review.\n"
        "• Group moderation: /mute, /unmute, /ban, /unban, /kick.\n"
        "• /blacklist and /unblacklist — owner-only trust controls.\n\n"
        "Commands: /start, /id, /help, /admin, /login, /setpass, /broadcast, /status, /report, /editpost"
    )


@dp.message(Command("id"))
@dp.message(F.text == "🪪 My ID")
async def show_id(message: Message):
    if message.from_user:
        await message.answer(
            f"<b>Your Telegram ID:</b> <code>{message.from_user.id}</code>\n"
            f"<b>Chat ID:</b> <code>{message.chat.id}</code>"
        )


@dp.message(Command("network"))
@dp.message(F.text == "🌐 Network")
async def network(message: Message):
    await message.answer("<b>GTS - GATES NETWORK</b>\nGates Official Bot channel and post tools.")


@dp.message(Command("admin"))
async def admin(message: Message):
    if not message.from_user or not can_manage(message.from_user.id):
        await message.answer("You don't have permission to open the management panel.")
        return
    await message.answer("<b>Management Panel</b>", reply_markup=admin_keyboard())


@dp.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: CallbackQuery, state: FSMContext):
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    if not callback.message:
        return
    if action == "connect":
        await begin_connect(callback.message, state)
    elif action == "create":
        await begin_post(callback.message, state)
    elif action == "verify":
        await begin_verification(callback.message, state)
    elif action == "id":
        await callback.message.answer(f"Your Telegram ID: <code>{callback.from_user.id}</code>")
    elif action == "network":
        await callback.message.answer("<b>GTS - GATES NETWORK</b>")


async def begin_connect(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ConnectState.channel)
    await message.answer("Send the channel @username or numeric channel ID. The bot and you must both be channel admins.")


@dp.message(F.text == "📢 Connect Channel")
async def connect_button(message: Message, state: FSMContext):
    await begin_connect(message, state)


@dp.message(ConnectState.channel)
async def receive_channel(message: Message, state: FSMContext):
    if not message.from_user or not message.text:
        await message.answer("Send a channel @username or numeric channel ID.")
        return
    ok, chat, error = await check_channel(message.text.strip(), message.from_user.id)
    if not ok:
        await message.answer(esc(error))
        return
    channel_id = str(chat.id)
    DB["channels"][channel_id] = {
        "id": chat.id,
        "title": chat.title or str(chat.id),
        "username": chat.username or "",
        "connected_by": message.from_user.id,
        "connected_at": now_iso(),
    }
    save_db()
    await state.clear()
    await message.answer(
        f"✅ <b>Channel connected</b>\nName: {esc(chat.title or 'Channel')}\n"
        f"ID: <code>{chat.id}</code>\n"
        f"Username: @{esc(chat.username) if chat.username else 'private channel'}"
    )


async def begin_post(message: Message, state: FSMContext):
    await state.clear()
    if not DB["channels"]:
        await message.answer("No channels connected. Use 📢 Connect Channel first.")
        return
    await state.set_state(PostState.channel)
    rows = ["Send the numeric ID of the connected channel:"]
    for cid, channel in DB["channels"].items():
        rows.append(f"• {esc(channel.get('title', cid))} — <code>{cid}</code>")
    await message.answer("\n".join(rows))


@dp.message(F.text == "📝 Create Post")
async def create_post_button(message: Message, state: FSMContext):
    await begin_post(message, state)


@dp.message(PostState.channel)
async def choose_post_channel(message: Message, state: FSMContext):
    if not message.from_user or not message.text:
        await message.answer("Send the channel ID from the list.")
        return
    cid = message.text.strip()
    channel = DB["channels"].get(cid)
    if not channel:
        await message.answer("That channel is not connected. Send one of the listed IDs.")
        return
    if channel.get("connected_by") != message.from_user.id and not can_manage(message.from_user.id):
        await message.answer("Only the channel connector or an approved manager can publish there.")
        return
    await state.update_data(channel_id=cid)
    await state.set_state(PostState.content)
    await message.answer("Send the post: plain text, a photo with caption, or a video with caption.")


@dp.message(PostState.content)
async def receive_post_content(message: Message, state: FSMContext):
    if message.photo:
        content = {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption or ""}
    elif message.video:
        content = {"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}
    elif message.text:
        content = {"type": "text", "text": message.text}
    else:
        await message.answer("Please send text, a photo, or a video.")
        return
    await state.update_data(content=content)
    await state.set_state(PostState.buttons)
    await message.answer(
        "Optional URL buttons. Use one button per line, or use | for buttons in the same row.\n"
        "<code>Website - https://example.com/</code>\n"
        "<code>Join - https://t.me/example - style:green</code>\n"
        "Example row: <code>Website - https://example.com/ | Channel - https://t.me/example - style:blue</code>\n\n"
        "Supported style labels: green, blue, red (Telegram client/API support may vary).\n"
        "Send <code>skip</code> if you don't want buttons."
    )


def parse_buttons(text: str) -> list[list[dict[str, str]]]:
    """Parse lines like `Text - https://example.com - style:green`; `|` groups buttons in a row."""
    if text.strip().lower() in {"skip", "none", "no", "cancel"}:
        return []
    rows: list[list[dict[str, str]]] = []
    for line in text.splitlines():
        row: list[dict[str, str]] = []
        for raw in line.split("|")[:3]:
            parts = [part.strip() for part in raw.split(" - ")]
            if len(parts) < 2:
                continue
            title, url = parts[0], parts[1]
            style = ""
            for extra in parts[2:]:
                if extra.lower().startswith("style:"):
                    style = extra.split(":", 1)[1].strip().lower()
            if title and url.startswith(("https://", "http://")):
                item = {"text": title[:64], "url": url}
                if style in {"green", "blue", "red"}:
                    item["style"] = style
                row.append(item)
        if row:
            rows.append(row)
    return rows[:12]


def post_markup(button_rows: list[list[dict[str, str]]]):
    if not button_rows:
        return None
    builder = InlineKeyboardBuilder()
    for row in button_rows:
        buttons = []
        for item in row[:3]:
            # InlineKeyboardButton.style is supported only by newer aiogram/Bot API versions.
            try:
                button = InlineKeyboardButton(text=item["text"], url=item["url"], style=item.get("style") or None)
            except (TypeError, ValueError):
                button = InlineKeyboardButton(text=item["text"], url=item["url"])
            buttons.append(button)
        if buttons:
            builder.row(*buttons)
    return builder.as_markup()


async def send_post(chat_id: int, content: dict[str, Any], markup=None):
    if content.get("type") == "text":
        return await bot.send_message(chat_id, content.get("text", ""), reply_markup=markup)
    if content.get("type") == "photo":
        return await bot.send_photo(chat_id, content["file_id"], caption=content.get("caption", ""), reply_markup=markup)
    if content.get("type") == "video":
        return await bot.send_video(chat_id, content["file_id"], caption=content.get("caption", ""), reply_markup=markup)
    raise ValueError("Unsupported post type")


@dp.message(PostState.buttons)
async def receive_post_buttons(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Send URL button lines or type skip.")
        return
    data = await state.get_data()
    buttons = parse_buttons(message.text)
    try:
        await send_post(message.chat.id, data["content"], post_markup(buttons))
    except (TelegramAPIError, KeyError, ValueError):
        await message.answer("Couldn't create preview. Please start again.")
        await state.clear()
        return
    await state.update_data(buttons=buttons)
    await state.set_state(PostState.confirm)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Publish", callback_data="post:publish"))
    kb.row(InlineKeyboardButton(text="Cancel", callback_data="post:cancel"))
    await message.answer(f"Preview sent above. Publish to <code>{esc(data.get('channel_id', ''))}</code>?", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "post:cancel")
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.answer("Post cancelled.")


@dp.callback_query(F.data == "post:publish")
async def publish_post(callback: CallbackQuery, state: FSMContext):
    if not callback.message:
        await callback.answer()
        return
    data = await state.get_data()
    cid = str(data.get("channel_id", ""))
    channel = DB["channels"].get(cid)
    if not channel or not data.get("content"):
        await state.clear()
        await callback.answer("Post expired. Start again.", show_alert=True)
        return
    if channel.get("connected_by") != callback.from_user.id and not can_manage(callback.from_user.id):
        await state.clear()
        await callback.answer("You cannot publish to this channel.", show_alert=True)
        return
    ok, chat, error = await check_channel(cid)
    if not ok:
        await callback.answer("Bot permissions are missing.", show_alert=True)
        await callback.message.answer(esc(error))
        return
    try:
        published = await send_post(chat.id, data["content"], post_markup(data.get("buttons", [])))
        DB["published_posts"][f"{chat.id}:{published.message_id}"] = {
            "channel_id": chat.id, "message_id": published.message_id,
            "created_by": callback.from_user.id, "content": data["content"],
            "buttons": data.get("buttons", []), "created_at": now_iso(),
        }
        save_db()
        await callback.answer("Published")
        await callback.message.answer(f"✅ Published to <b>{esc(chat.title or chat.id)}</b>. Message ID: <code>{published.message_id}</code>\nUse /editpost to edit this post later.")
    except TelegramAPIError as exc:
        log.warning("Publish failed: %s", exc)
        await callback.answer("Publishing failed; check bot permissions.", show_alert=True)
    await state.clear()


async def begin_verification(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(VerifyState.details)
    await message.answer(
        "<b>GTS Verification Application</b>\nPlease send one message answering these questions:\n\n"
        "1. Telegram username and user ID\n"
        "2. What service or activity are you being verified for?\n"
        "3. Vouch channel/link (if available)\n"
        "4. Past work channels, previous projects, or references\n"
        "5. How long have you been active?\n"
        "6. Any public proof, feedback, or transaction references?\n"
        "7. Any additional details the reviewer should know?\n\n"
        "Be truthful. Applications are reviewed by the owner; verification is not a guarantee against scams."
    )


@dp.message(F.text == "✅ Verification")
async def verification_button(message: Message, state: FSMContext):
    await begin_verification(message, state)


@dp.message(VerifyState.details)
async def submit_verification(message: Message, state: FSMContext):
    if not message.from_user:
        return
    details = message.text or message.caption or "[Media submitted]"
    key = str(message.from_user.id)
    DB["pending_verifications"][key] = {
        "user_id": message.from_user.id,
        "name": message.from_user.full_name,
        "username": message.from_user.username or "",
        "details": details[:3000],
        "submitted_at": now_iso(),
    }
    save_db()
    await state.clear()
    await message.answer("Your verification request was submitted and is pending owner review.")
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Approve", callback_data=f"verify:approve:{key}"),
        InlineKeyboardButton(text="Reject", callback_data=f"verify:reject:{key}"),
    )
    try:
        await bot.send_message(
            OWNER_ID,
            f"<b>Verification request</b>\nName: {esc(message.from_user.full_name)}\n"
            f"ID: <code>{key}</code>\nUsername: @{esc(message.from_user.username or 'none')}\n"
            f"Details:\n{esc(details[:3000])}",
            reply_markup=kb.as_markup(),
        )
    except TelegramAPIError:
        log.exception("Could not notify owner about verification")


@dp.callback_query(F.data.startswith("verify:"))
async def decide_verification(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid request")
        return
    action, key = parts[1], parts[2]
    if key not in DB["pending_verifications"]:
        await callback.answer("Request is no longer pending", show_alert=True)
        return
    if action == "approve":
        DB["users"].setdefault(key, {"id": int(key), "verified": False})
        DB["users"][key]["verified"] = True
        note = "Your verification request has been approved."
    elif action == "reject":
        note = "Your verification request was not approved. You may submit a new request."
    else:
        await callback.answer("Invalid action")
        return
    DB["pending_verifications"].pop(key, None)
    save_db()
    try:
        await bot.send_message(int(key), note)
    except TelegramAPIError:
        pass
    await callback.answer("Processed")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"Verification request for <code>{esc(key)}</code> processed.")


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()
    return salt, digest


def password_matches(password: str, salt: str, expected: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt)[1], expected)


@dp.message(Command("setpass"))
async def set_password(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("Only the owner can create moderator credentials.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Usage: <code>/setpass USER_ID PASSWORD</code> (password at least 8 characters)")
        return
    try:
        target_id = int(parts[1])
    except ValueError:
        await message.answer("USER_ID must be numeric.")
        return
    password = parts[2]
    if len(password) < 8:
        await message.answer("Password must be at least 8 characters.")
        return
    salt, digest = hash_password(password)
    DB["moderators"][str(target_id)] = {"salt": salt, "password_hash": digest, "approved": False, "created_at": now_iso()}
    DB["pending_moderators"][str(target_id)] = {"user_id": target_id, "requested_at": now_iso()}
    save_db()
    try:
        await bot.send_message(target_id, "The owner created moderator credentials for you. Use /login and enter the password privately; the owner must approve access.")
    except TelegramAPIError:
        pass
    await message.answer(f"Credentials saved for <code>{target_id}</code>. They must /login, then approve their request in /admin.")


@dp.message(Command("login"))
async def login(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(LoginState.password)
    await message.answer("Send your moderator password in this private chat.")


@dp.message(LoginState.password)
async def login_password(message: Message, state: FSMContext):
    if not message.from_user or not message.text:
        await message.answer("Send the password as text.")
        return
    key = str(message.from_user.id)
    record = DB["moderators"].get(key)
    if not record or not password_matches(message.text.strip(), record["salt"], record["password_hash"]):
        await state.clear()
        await message.answer("Incorrect password. Ask the owner if you need moderator access.")
        return
    if record.get("approved"):
        await state.clear()
        await message.answer("You are already an approved moderator. Use /admin.")
        return
    DB["pending_moderators"][key] = {"user_id": message.from_user.id, "requested_at": now_iso()}
    save_db()
    await state.clear()
    await message.answer("Password accepted. Your access is awaiting owner approval.")
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="Approve", callback_data=f"mod:approve:{key}"),
        InlineKeyboardButton(text="Reject", callback_data=f"mod:reject:{key}"),
    )
    try:
        await bot.send_message(OWNER_ID, f"<b>Moderator approval request</b>\nName: {esc(message.from_user.full_name)}\nID: <code>{key}</code>", reply_markup=kb.as_markup())
    except TelegramAPIError:
        log.exception("Could not notify owner about moderator request")


@dp.callback_query(F.data.startswith("mod:"))
async def decide_moderator(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid request")
        return
    action, key = parts[1], parts[2]
    if key not in DB["moderators"]:
        await callback.answer("Moderator record not found", show_alert=True)
        return
    if action == "approve":
        DB["moderators"][key]["approved"] = True
        DB["pending_moderators"].pop(key, None)
        note = "Your moderator access has been approved."
    elif action == "reject":
        DB["moderators"].pop(key, None)
        DB["pending_moderators"].pop(key, None)
        note = "Your moderator access request was rejected."
    else:
        await callback.answer("Invalid action")
        return
    save_db()
    try:
        await bot.send_message(int(key), note)
    except TelegramAPIError:
        pass
    await callback.answer("Processed")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"Moderator request for <code>{esc(key)}</code> processed.")


@dp.callback_query(F.data == "owner:mods")
async def owner_mods(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True)
        return
    await callback.answer()
    ids = list(DB["pending_moderators"])
    await callback.message.answer("Pending moderators:\n" + ("\n".join(f"• <code>{esc(x)}</code>" for x in ids) if ids else "None"))


@dp.callback_query(F.data == "owner:verify")
async def owner_verifications(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True)
        return
    await callback.answer()
    ids = list(DB["pending_verifications"])
    await callback.message.answer("Pending verifications:\n" + ("\n".join(f"• <code>{esc(x)}</code>" for x in ids) if ids else "None"))


@dp.callback_query(F.data == "owner:stats")
async def owner_stats(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True)
        return
    await callback.answer()
    approved = sum(1 for row in DB["moderators"].values() if row.get("approved"))
    await callback.message.answer(
        "<b>Bot Statistics</b>\n"
        f"Users: {len(DB['users'])}\nChannels: {len(DB['channels'])}\n"
        f"Approved moderators: {approved}\nPending moderators: {len(DB['pending_moderators'])}\n"
        f"Pending verifications: {len(DB['pending_verifications'])}"
    )


@dp.callback_query(F.data == "owner:broadcast")
async def begin_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True)
        return
    await callback.answer()
    await state.set_state(BroadcastState.text)
    await callback.message.answer("Send the text to broadcast to users who have started the bot.")


@dp.message(Command("broadcast"))
async def begin_broadcast_command(message: Message, state: FSMContext):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("Only the owner can broadcast.")
        return
    await state.clear()
    await state.set_state(BroadcastState.text)
    await message.answer("Send the text to broadcast to users who have started the bot.")


@dp.message(BroadcastState.text)
async def receive_broadcast(message: Message, state: FSMContext):
    if not message.from_user or not is_owner(message.from_user.id):
        await state.clear()
        return
    if not message.text:
        await message.answer("Text broadcasts only. Please send a text message.")
        return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastState.confirm)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Send broadcast", callback_data="broadcast:send"))
    kb.row(InlineKeyboardButton(text="Cancel", callback_data="broadcast:cancel"))
    await message.answer(f"<b>Broadcast preview</b>\n\n{esc(message.text[:3500])}\n\nRecipients: {len(DB['users'])}\nSend now?", reply_markup=kb.as_markup())


@dp.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Cancelled")
    if callback.message:
        await callback.message.answer("Broadcast cancelled.")


@dp.callback_query(F.data == "broadcast:send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True)
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await state.clear()
        await callback.answer("Broadcast expired. Start again.", show_alert=True)
        return
    await callback.answer("Broadcast started")
    sent = failed = 0
    for user_id in list(DB["users"]):
        try:
            await bot.send_message(int(user_id), text)
            sent += 1
        except TelegramAPIError:
            failed += 1
        await asyncio.sleep(0.04)
    await state.clear()
    if callback.message:
        await callback.message.answer(f"Broadcast finished.\nSent: {sent}\nFailed: {failed}")


# ---------------- Group moderation ----------------
async def command_target(message: Message, args: list[str]) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    if args:
        token = args[0].strip()
        if token.isdigit():
            return int(token)
        if token.startswith("@"):
            try:
                chat = await bot.get_chat(token)
                return chat.id
            except TelegramAPIError:
                return None
    return None


async def group_admin_allowed(message: Message) -> bool:
    if not message.from_user or message.chat.type not in {"group", "supergroup"}:
        await message.answer("Use this command inside a group or supergroup.")
        return False
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in {"administrator", "creator"} and not is_owner(message.from_user.id):
            await message.answer("Only group administrators can use this command.")
            return False
        me = await bot.get_me()
        bot_member = await bot.get_chat_member(message.chat.id, me.id)
        if bot_member.status != "administrator":
            await message.answer("Please promote the bot to group administrator and grant Restrict Members permission.")
            return False
        return True
    except TelegramAPIError:
        await message.answer("I couldn't check admin permissions. Make sure I'm an administrator.")
        return False


async def moderate_member(message: Message, action: str, duration: int | None = None):
    args = (message.text or "").split()[1:]
    if not await group_admin_allowed(message):
        return
    target_id = await command_target(message, args)
    if target_id is None:
        await message.answer(f"Reply to a member's message or use /{action} USER_ID" + (" [minutes]" if action == "mute" else "") + ".")
        return
    if target_id == OWNER_ID:
        await message.answer("I won't moderate the bot owner.")
        return
    try:
        target = await bot.get_chat_member(message.chat.id, target_id)
        if target.status in {"administrator", "creator"}:
            await message.answer("I won't moderate another group administrator.")
            return
        if action == "mute":
            from datetime import timedelta
            until = None
            if duration and duration > 0:
                until = datetime.now(timezone.utc) + timedelta(minutes=min(duration, 10080))
            from aiogram.types import ChatPermissions
            await bot.restrict_chat_member(message.chat.id, target_id, ChatPermissions(can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False), until_date=until)
            result = f"Muted <code>{target_id}</code>" + (f" for {min(duration, 10080)} minute(s)." if duration else ".")
        elif action == "unmute":
            from aiogram.types import ChatPermissions
            await bot.restrict_chat_member(message.chat.id, target_id, ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
            result = f"Unmuted <code>{target_id}</code>."
        elif action == "ban":
            await bot.ban_chat_member(message.chat.id, target_id)
            result = f"Banned <code>{target_id}</code>."
        elif action == "unban":
            await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            result = f"Unbanned <code>{target_id}</code>."
        elif action == "kick":
            await bot.ban_chat_member(message.chat.id, target_id)
            await bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            result = f"Kicked <code>{target_id}</code>."
        else:
            return
        await message.answer(result)
    except TelegramAPIError as exc:
        log.warning("Moderation %s failed: %s", action, exc)
        await message.answer("Action failed. Check the bot's administrator permissions and target ID.")


@dp.message(Command("mute"))
async def mute_command(message: Message):
    args = (message.text or "").split()[1:]
    duration = None
    if args and args[-1].isdigit() and len(args) >= 2:
        try:
            duration = int(args[-1])
            args = args[:-1]
        except ValueError:
            pass
    # Keep target extraction simple: /mute USER_ID [minutes], or reply to a member.
    original = message.text
    if duration is not None and args:
        message.text = "/mute " + " ".join(args)
    await moderate_member(message, "mute", duration)
    message.text = original


@dp.message(Command("unmute"))
async def unmute_command(message: Message): await moderate_member(message, "unmute")
@dp.message(Command("ban"))
async def ban_command(message: Message): await moderate_member(message, "ban")
@dp.message(Command("unban"))
async def unban_command(message: Message): await moderate_member(message, "unban")
@dp.message(Command("kick"))
async def kick_command(message: Message): await moderate_member(message, "kick")


# ---------------- Trust/status checker and reports ----------------
def get_status(user_id: int) -> tuple[str, str]:
    key = str(user_id)
    if key in DB["blacklist"]:
        return "BLACKLISTED", str(DB["blacklist"][key].get("reason", "Owner action"))
    user = DB["users"].get(key, {})
    if user.get("verified"):
        return "VERIFIED", "Verification approved by the GTS owner"
    if DB["reports"].get(key):
        return "REPORTED — UNDER REVIEW", f"Reports received: {len(DB['reports'][key])}"
    return "NOT VERIFIED", "No approved verification record found"


@dp.message(Command("status"))
async def status_command(message: Message):
    args = (message.text or "").split()[1:]
    target = await command_target(message, args)
    if target is None:
        target = message.from_user.id if message.from_user else None
    if target is None:
        await message.answer("Usage: /status USER_ID, or reply to a member with /status.")
        return
    status, reason = get_status(target)
    await message.answer(f"<b>GTS Trust Status</b>\nUser ID: <code>{target}</code>\nStatus: <b>{esc(status)}</b>\nDetails: {esc(reason)}\n\nA VERIFIED label means the owner approved a submission; it is not a guarantee that a user is risk-free.")


@dp.message(Command("report"))
async def report_command(message: Message, state: FSMContext):
    args = (message.text or "").split()[1:]
    target = await command_target(message, args)
    if target is None:
        await state.clear()
        await state.set_state(ReportState.target)
        await message.answer("Send the Telegram user ID or @username of the person you want to report.")
        return
    if message.from_user and target == message.from_user.id:
        await message.answer("You cannot report yourself.")
        return
    await state.update_data(report_target=target)
    await state.set_state(ReportState.reason)
    await message.answer("Send the report reason with any relevant evidence, transaction details, or message links. Do not send passwords or private credentials.")


@dp.message(ReportState.target)
async def report_target_received(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    target = None
    if raw.isdigit(): target = int(raw)
    elif raw.startswith("@"):
        try: target = (await bot.get_chat(raw)).id
        except TelegramAPIError: target = None
    if target is None:
        await message.answer("I couldn't resolve that user. Send a numeric Telegram user ID.")
        return
    if message.from_user and target == message.from_user.id:
        await message.answer("You cannot report yourself.")
        await state.clear()
        return
    await state.update_data(report_target=target)
    await state.set_state(ReportState.reason)
    await message.answer("Now send the report reason and any relevant evidence or message links.")


@dp.message(ReportState.reason)
async def report_reason_received(message: Message, state: FSMContext):
    if not message.from_user:
        await state.clear(); return
    data = await state.get_data()
    target = int(data.get("report_target", 0))
    reason = (message.text or message.caption or "").strip()
    if not target or len(reason) < 8:
        await message.answer("Please provide a clear reason of at least 8 characters.")
        return
    key = str(target)
    reports = DB["reports"].setdefault(key, [])
    # Avoid duplicate reports from the same reporter.
    if any(int(row.get("reporter_id", 0)) == message.from_user.id for row in reports):
        await message.answer("You have already reported this user. Additional reports from the same account won't be counted.")
        await state.clear(); return
    reports.append({"reporter_id": message.from_user.id, "reason": reason[:2500], "reported_at": now_iso()})
    # A single report is displayed as reported/under review, not auto-blacklisted, to reduce malicious false reports.
    save_db(); await state.clear()
    await message.answer(f"Report submitted. User <code>{target}</code> will show as <b>REPORTED — UNDER REVIEW</b> until the owner reviews the case. Reports are not proof by themselves.")
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="Blacklist user", callback_data=f"report:blacklist:{target}"), InlineKeyboardButton(text="Dismiss report", callback_data=f"report:dismiss:{target}"))
    try:
        await bot.send_message(OWNER_ID, f"<b>New user report</b>\nReported user: <code>{target}</code>\nReporter: <code>{message.from_user.id}</code>\nReason: {esc(reason[:2500])}\nTotal reports: {len(reports)}", reply_markup=kb.as_markup())
    except TelegramAPIError: log.exception("Could not notify owner of report")


@dp.callback_query(F.data.startswith("report:"))
async def owner_review_report(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Owner only", show_alert=True); return
    _, action, target = callback.data.split(":", 2)
    if action == "blacklist":
        rows = DB["reports"].get(target, [])
        DB["blacklist"][target] = {"reason": rows[-1].get("reason", "Owner-reviewed report") if rows else "Owner-reviewed report", "blacklisted_at": now_iso(), "reports_count": len(rows)}
        save_db(); result = f"User {target} is now BLACKLISTED."
    elif action == "dismiss":
        DB["reports"].pop(target, None); save_db(); result = f"Reports for {target} were dismissed."
    else:
        await callback.answer("Invalid action"); return
    await callback.answer("Saved")
    if callback.message:
        await callback.message.answer(result)


@dp.message(Command("blacklist"))
async def blacklist_command(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("Owner only."); return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit():
        await message.answer("Usage: /blacklist USER_ID REASON"); return
    DB["blacklist"][parts[1]] = {"reason": parts[2][:1000], "blacklisted_at": now_iso(), "reports_count": len(DB["reports"].get(parts[1], []))}
    save_db(); await message.answer(f"User <code>{parts[1]}</code> is now blacklisted.")


@dp.message(Command("unblacklist"))
async def unblacklist_command(message: Message):
    if not message.from_user or not is_owner(message.from_user.id):
        await message.answer("Owner only."); return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /unblacklist USER_ID"); return
    DB["blacklist"].pop(parts[1], None); save_db(); await message.answer(f"Blacklist entry removed for <code>{parts[1]}</code>.")


# ---------------- Edit a previously published post ----------------
@dp.message(Command("editpost"))
async def edit_post_start(message: Message, state: FSMContext):
    if not message.from_user:
        return
    await state.clear()
    await state.set_state(EditPostState.channel)
    rows = ["Send the connected channel ID for the post you want to edit:"]
    rows += [f"• {esc(ch.get('title', cid))} — <code>{cid}</code>" for cid, ch in DB["channels"].items() if ch.get("connected_by") == message.from_user.id or can_manage(message.from_user.id)]
    await message.answer("\n".join(rows) if len(rows) > 1 else "No connected channels you can edit. Connect one first.")


@dp.message(EditPostState.channel)
async def edit_post_channel(message: Message, state: FSMContext):
    cid = (message.text or "").strip()
    ch = DB["channels"].get(cid)
    if not ch or (ch.get("connected_by") != (message.from_user.id if message.from_user else 0) and not can_manage(message.from_user.id if message.from_user else 0)):
        await message.answer("Channel not found or you don't have permission. Send a listed channel ID."); return
    await state.update_data(edit_channel_id=cid); await state.set_state(EditPostState.message_id)
    await message.answer("Send the message ID of the post to edit. The bot can edit only messages it originally published and recorded.")


@dp.message(EditPostState.message_id)
async def edit_post_message_id(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    data = await state.get_data(); cid = str(data.get("edit_channel_id", ""))
    if not raw.isdigit() or f"{cid}:{raw}" not in DB["published_posts"]:
        await message.answer("I couldn't find that published message in this channel. Check the message ID."); return
    await state.update_data(edit_message_id=int(raw)); await state.set_state(EditPostState.content)
    await message.answer("Send the replacement post text, or a photo/video with caption. Editing across media types may not be supported by Telegram.")


@dp.message(EditPostState.content)
async def edit_post_content(message: Message, state: FSMContext):
    if message.photo:
        content = {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption or ""}
    elif message.video:
        content = {"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}
    elif message.text:
        content = {"type": "text", "text": message.text}
    else:
        await message.answer("Send text, photo, or video."); return
    await state.update_data(edit_content=content); await state.set_state(EditPostState.buttons)
    await message.answer("Send the replacement URL buttons using the format shown below, or type skip to remove all buttons:\n<code>Button text - https://example.com/ - style:green</code>\nUse | to put up to three buttons in one row.")


@dp.message(EditPostState.buttons)
async def edit_post_buttons(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Send URL buttons or type skip."); return
    data = await state.get_data(); cid = int(data["edit_channel_id"]); mid = int(data["edit_message_id"])
    buttons = parse_buttons(message.text)
    content = data["edit_content"]
    try:
        markup = post_markup(buttons)
        if content["type"] == "text":
            await bot.edit_message_text(chat_id=cid, message_id=mid, text=content["text"], reply_markup=markup)
        elif content["type"] == "photo":
            from aiogram.types import InputMediaPhoto
            await bot.edit_message_media(chat_id=cid, message_id=mid, media=InputMediaPhoto(media=content["file_id"], caption=content.get("caption", "")), reply_markup=markup)
        else:
            from aiogram.types import InputMediaVideo
            await bot.edit_message_media(chat_id=cid, message_id=mid, media=InputMediaVideo(media=content["file_id"], caption=content.get("caption", "")), reply_markup=markup)
        key = f"{cid}:{mid}"; DB["published_posts"][key]["content"] = content; DB["published_posts"][key]["buttons"] = buttons; DB["published_posts"][key]["edited_at"] = now_iso(); save_db()
        await message.answer("Post updated successfully.")
    except TelegramAPIError as exc:
        log.warning("Post edit failed: %s", exc)
        await message.answer("Edit failed. Telegram may not allow this media conversion, or the bot may lack edit permissions. Try editing text with text, or photo/video with the same media type.")
    await state.clear()


async def main():
    runner = await health_server()
    try:
        me = await bot.get_me()
        log.info("Starting @%s (ID %s)", me.username, me.id)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
