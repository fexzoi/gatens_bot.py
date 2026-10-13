import asyncio
import json
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from passlib.hash import pbkdf2_sha256

# Configured credentials
TOKEN = os.getenv("BOT_TOKEN", "8841797167:AAGqfC5laKal7Z7D_Q_PVDQJa7sQRri9BIY")
OWNER_ID = 8480522053

# Initialize Bot and Dispatcher
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

# --- PERSISTENT DATABASE MANAGEMENT ---
DB_FILE = "gatens_database.json"

def load_database():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "verifications": {}, 
        "users": {}, 
        "broadcast_targets": {}, 
        "admins": {}
    }

def save_database(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save database: {e}")

# Ensure initial admin/owner exists in database on startup
def init_owner_account():
    db = load_database()
    if str(OWNER_ID) not in db["admins"]:
        db["admins"][str(OWNER_ID)] = {
            "username": "Owner",
            "password_hash": pbkdf2_sha256.hash("ownerdefault"),
            "is_approved": 1,
            "role": "owner"
        }
        save_database(db)

init_owner_account()

# Active logged-in admin sessions
active_admin_sessions = set()

# --- FSM STATES ---
class VerificationSG(StatesGroup):
    selecting_group = State()
    uploading_userid = State()
    uploading_vouch = State()

class BroadcastSG(StatesGroup):
    choosing_target = State()
    waiting_for_message = State()

class AdminAuthSG(StatesGroup):
    register_pass = State()
    login_pass = State()

class PostCreatorSG(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_buttons = State()


# --- DUMMY WEB SERVER (For Render + Cron-Job 24/7 uptime) ---
async def handle_ping(request):
    return web.Response(text="Gatens Network Hub is active and running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server started on port {port}")


# --- KEYBOARDS ---

def get_join_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="MAIN CHANNEL", url="https://t.me/+3jHzHttnfHFlZWFh"),
                InlineKeyboardButton(text="REDIRECT CH", url="https://t.me/gatens"),
            ],
            [
                InlineKeyboardButton(text="CHAT GC", url="https://t.me/chatyear"),
                InlineKeyboardButton(text="BUY & SELL", url="https://t.me/fragte"),
            ],
            [
                InlineKeyboardButton(text="MARKET HUB", url="https://t.me/whiteages"),
                InlineKeyboardButton(text="OTHER BOTS", callback_data="show_bots"),
            ],
            [
                InlineKeyboardButton(text="« BACK TO MAIN MENU", callback_data="main_menu")
            ],
        ]
    )

def get_group_selection_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="CHAT GC (@chatyear)", callback_data="verify_group_chatyear"),
                InlineKeyboardButton(text="BUY & SELL (@fragte)", callback_data="verify_group_fragte"),
            ],
            [
                InlineKeyboardButton(text="MARKET HUB (@whiteages)", callback_data="verify_group_whiteages"),
                InlineKeyboardButton(text="« CANCEL", callback_data="main_menu"),
            ],
        ]
    )

def get_main_menu_keyboard(is_admin: bool):
    buttons = [
        [
            InlineKeyboardButton(text="VERIFY ACCOUNT", callback_data="start_verification"),
            InlineKeyboardButton(text="NETWORK HUBS", callback_data="view_hubs"),
        ],
        [
            InlineKeyboardButton(text="📝 CREATE POST", callback_data="start_create_post")
        ]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(text="[ADMIN PANEL]", callback_data="admin_panel"),
            InlineKeyboardButton(text="BROADCAST", callback_data="admin_broadcast"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- AUTO-DISCOVER CHATS/GROUPS/CHANNELS FOR BROADCAST ---
@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def auto_track_network_chats(message: types.Message):
    chat = message.chat
    db = load_database()
    chat_id_str = str(chat.id)
    if chat_id_str not in db["broadcast_targets"]:
        db["broadcast_targets"][chat_id_str] = {
            "title": chat.title or "Unnamed Chat",
            "type": chat.type
        }
        save_database(db)


# --- HANDLERS: START & MAIN MENU ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    is_admin = (message.from_user.id in ADMIN_IDS) or (user_id in active_admin_sessions)

    db = load_database()
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": user_name,
            "joined": str(message.date),
            "status": "unverified",
            "verified_chats": [],
        }
        save_database(db)

    if "verified_chats" not in db["users"][user_id]:
        db["users"][user_id]["verified_chats"] = []
        save_database(db)

    status_label = db["users"][user_id]["status"].upper()

    text = (
        f"<b>GATENS NETWORK INFRASTRUCTURE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"USER: <code>{user_name}</code>\n"
        f"STATUS: <b>[{status_label}]</b>\n\n"
        f"<b>MANDATORY INSTRUCTION:</b>\n"
        f"You must verify your account in the Gatens Network before interacting with community groups and markets.\n\n"
        f"Select an option below to proceed:"
    )

    await message.answer(
        text,
        reply_markup=get_main_menu_keyboard(is_admin),
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = str(callback.from_user.id)
    is_admin = (callback.from_user.id in ADMIN_IDS) or (user_id in active_admin_sessions)

    db = load_database()
    status_label = (
        db.get("users", {})
        .get(user_id, {})
        .get("status", "unverified")
        .upper()
    )

    text = (
        f"<b>GATENS NETWORK HUB</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"STATUS: <b>[{status_label}]</b>\n"
        "Select an action below:"
    )
    await callback.message.edit_text(
        text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "view_hubs")
async def process_view_hubs(callback: types.CallbackQuery):
    text = (
        "<b>OFFICIAL NETWORK HUBS & CHANNELS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Access our verified channels, community groups, and markets below:"
    )
    await callback.message.edit_text(
        text, reply_markup=get_join_keyboard(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "show_bots")
async def process_show_bots(callback: types.CallbackQuery):
    text = (
        "<b>GATENS ECOSYSTEM BOTS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Core Infrastructure Bot: <code>@gatens_bot</code>\n"
        "• More specialized network utilities coming online."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="« BACK TO DESTINATIONS", callback_data="view_hubs")
        ]]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


# --- OWNER-APPROVED CUSTOM PASSWORD ADMIN LOGIN SYSTEM ---

@dp.message(Command("setpass"))
async def cmd_setpass(message: types.Message, state: FSMContext):
    await message.answer("🔑 **Admin Registration**\nSend the custom password you want to set for your admin panel access:")
    await state.set_state(AdminAuthSG.register_pass)

@dp.message(AdminAuthSG.register_pass, F.text)
async def process_register_pass(message: types.Message, state: FSMContext):
    user = message.from_user
    password = message.text.strip()
    hashed = pbkdf2_sha256.hash(password)

    db = load_database()
    db["admins"][str(user.id)] = {
        "username": user.username or user.first_name,
        "password_hash": hashed,
        "is_approved": 0,
        "role": "mod"
    }
    save_database(db)

    await message.answer("✅ Password registered! Your request has been sent to the Owner for approval.")
    await state.clear()

    # Notify Owner
    approval_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_admin_{user.id}"),
            InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_admin_{user.id}")
        ]]
    )
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"🔔 **New Admin Registration Request**\nUser: @{user.username or 'No Username'}\nID: `{user.id}`",
            parse_mode="HTML",
            reply_markup=approval_keyboard
        )
    except Exception as e:
        logging.error(f"Failed to notify owner: {e}")

@dp.callback_query(F.data
