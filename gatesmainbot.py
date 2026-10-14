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
        "Commands: /start, /id, /help, /admin, /login, /setpass, /broadcast"
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
        "Optional URL buttons, one per line:\n<code>Button title | https://example.com</code>\n\n"
        "Send <code>skip</code> if you don't want buttons."
    )


def parse_buttons(text: str) -> list[dict[str, str]]:
    if text.strip().lower() in {"skip", "none", "no"}:
        return []
    result = []
    for line in text.splitlines():
        if "|" not in line:
            continue
        title, url = (part.strip() for part in line.split("|", 1))
        if title and url.startswith(("https://", "http://")):
            result.append({"text": title[:64], "url": url})
    return result[:12]


def post_markup(buttons: list[dict[str, str]]):
    if not buttons:
        return None
    builder = InlineKeyboardBuilder()
    for item in buttons:
        builder.row(InlineKeyboardButton(text=item["text"], url=item["url"]))
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
        await send_post(chat.id, data["content"], post_markup(data.get("buttons", [])))
        await callback.answer("Published")
        await callback.message.answer(f"✅ Published to <b>{esc(chat.title or chat.id)}</b>.")
    except TelegramAPIError as exc:
        log.warning("Publish failed: %s", exc)
        await callback.answer("Publishing failed; check bot permissions.", show_alert=True)
    await state.clear()


async def begin_verification(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(VerifyState.details)
    await message.answer("Send your verification reason and any relevant channel @username. The owner will review it.")


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
