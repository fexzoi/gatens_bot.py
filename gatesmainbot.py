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

# Credentials
TOKEN = os.getenv("BOT_TOKEN", "8841797167:AAGqfC5laKal7Z7D_Q_PVDQJa7sQRri9BIY")
OWNER_ID = 8480522053

# Initialize
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

# --- DATABASE MANAGEMENT ---
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
        "channels": {},
        "broadcast_targets": {},
        "admins": {}
    }

def save_database(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save database: {e}")

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
active_admin_sessions = set()

def is_user_verified(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    db = load_database()
    user_str = str(user_id)
    if user_str in db.get("users", {}):
        return db["users"][user_str].get("status") == "verified"
    return False


# --- STATES ---
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

class ChannelSG(StatesGroup):
    waiting_for_channel = State()

class PostCreatorSG(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    waiting_for_buttons = State()
    choosing_target_channel = State()


# --- UPTIME WEB SERVER ---
async def handle_ping(request):
    return web.Response(text="Gatens Network Hub Active")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


# --- KEYBOARDS ---
def get_main_menu_keyboard(is_admin: bool):
    buttons = [
        [InlineKeyboardButton(text="VERIFY ACCOUNT", callback_data="start_verification"), InlineKeyboardButton(text="NETWORK HUBS", callback_data="view_hubs")],
        [InlineKeyboardButton(text="CREATE POST", callback_data="start_create_post"), InlineKeyboardButton(text="ADD CHANNEL", callback_data="add_channel")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="ADMIN PANEL", callback_data="admin_panel"), InlineKeyboardButton(text="BROADCAST", callback_data="admin_broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_join_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="MAIN CHANNEL", url="https://t.me/+3jHzHttnfHFlZWFh"), InlineKeyboardButton(text="REDIRECT CH", url="https://t.me/gatens")],
        [InlineKeyboardButton(text="CHAT GC", url="https://t.me/chatyear"), InlineKeyboardButton(text="BUY & SELL", url="https://t.me/fragte")],
        [InlineKeyboardButton(text="MARKET HUB", url="https://t.me/whiteages")],
        [InlineKeyboardButton(text="BACK TO MAIN MENU", callback_data="main_menu")]
    ])


# --- USER COMMANDS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_str = str(user_id)
    user_name = message.from_user.first_name
    is_admin = (user_id == OWNER_ID) or (user_str in active_admin_sessions)

    db = load_database()
    if user_str not in db["users"]:
        status = "verified" if user_id == OWNER_ID else "unverified"
        db["users"][user_str] = {"name": user_name, "joined": str(message.date), "status": status, "verified_chats": []}
        save_database(db)

    verified = is_user_verified(user_id)
    status_label = "VERIFIED" if verified else db["users"][user_str].get("status", "unverified").upper()

    text = f"<b>GATENS NETWORK INFRASTRUCTURE</b>\nUser: <code>{user_name}</code>\nStatus: <b>[{status_label}]</b>\n\nSelect an option to proceed:"
    await message.answer(text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    user_str = str(user_id)
    is_admin = (user_id == OWNER_ID) or (user_str in active_admin_sessions)
    
    verified = is_user_verified(user_id)
    db = load_database()
    status_label = "VERIFIED" if verified else db.get("users", {}).get(user_str, {}).get("status", "unverified").upper()

    text = f"<b>GATENS NETWORK HUB</b>\nStatus: <b>[{status_label}]</b>\nSelect an action below:"
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "view_hubs")
async def process_view_hubs(callback: types.CallbackQuery):
    text = "<b>OFFICIAL NETWORK HUBS & CHANNELS</b>\nAccess network destinations below:"
    await callback.message.edit_text(text, reply_markup=get_join_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.message(Command("network"))
async def cmd_network_info(message: types.Message):
    text = "<b>GATENS NETWORK DIRECTORY</b>\nSupport Portal: <code>@gatens</code>\nStatus: Operational"
    await message.answer(text, parse_mode="HTML")


# --- CHANNEL BINDING SYSTEM ---

@dp.callback_query(F.data == "add_channel")
@dp.message(Command("addchannel"))
async def cmd_add_channel(event: types.Message | types.CallbackQuery, state: FSMContext):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    text = (
        "<b>ADD CHANNEL / GROUP</b>\n\n"
        "1. Add this bot as Administrator in your channel or group.\n"
        "2. Forward any message from that channel here, OR send the Channel Username (e.g., <code>@mychannel</code>) or Channel ID."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="CANCEL", callback_data="main_menu")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(ChannelSG.waiting_for_channel)

@dp.message(ChannelSG.waiting_for_channel)
async def process_channel_input(message: types.Message, state: FSMContext):
    target_chat_id = None

    if message.forward_from_chat:
        target_chat_id = message.forward_from_chat.id
    elif message.text:
        target_chat_id = message.text.strip()

    if not target_chat_id:
        await message.answer("Invalid input. Forward a message from your channel or send the channel username.")
        return

    try:
        chat = await bot.get_chat(target_chat_id)
        member = await bot.get_chat_member(chat.id, bot.id)
        
        if member.status not in ["administrator", "creator"]:
            await message.answer("Bot is not an Administrator in this chat. Make the bot admin and try again.")
            return

        db = load_database()
        user_str = str(message.from_user.id)
        
        db["channels"][str(chat.id)] = {
            "title": chat.title or chat.username or str(chat.id),
            "username": chat.username,
            "id": chat.id,
            "added_by": user_str
        }
        save_database(db)

        await message.answer(f"Channel <b>{chat.title}</b> successfully bound to your account and ready for posting.", parse_mode="HTML")
        await state.clear()
    except Exception as e:
        await message.answer(f"Failed to register channel: {e}. Ensure the bot is added as admin.")

@dp.message(Command("mychannels"))
async def cmd_my_channels(message: types.Message):
    user_str = str(message.from_user.id)
    db = load_database()
    channels = db.get("channels", {})
    
    user_channels = [ch for ch in channels.values() if ch.get("added_by") == user_str or message.from_user.id == OWNER_ID]

    if not user_channels:
        await message.answer("You have not added any channels yet. Use /addchannel to bind one.")
        return

    text = "<b>YOUR CONNECTED CHANNELS:</b>\n"
    for ch in user_channels:
        text += f"• {ch['title']} (<code>{ch['id']}</code>)\n"

    await message.answer(text, parse_mode="HTML")


# --- CONTROLLER POST CREATOR (OPEN FOR USERS) ---

@dp.callback_query(F.data == "start_create_post")
@dp.message(Command("createpost"))
async def cmd_create_post(event: types.Message | types.CallbackQuery, state: FSMContext):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    if isinstance(event, types.CallbackQuery):
        await event.answer()

    text = "<b>CONTROLLER POST CREATOR</b>\nStep 1/3: Send the text or caption for your post."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="CANCEL", callback_data="main_menu")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PostCreatorSG.waiting_for_text)

@dp.message(PostCreatorSG.waiting_for_text, F.text)
async def process_post_text(message: types.Message, state: FSMContext):
    await state.update_data(post_text=message.text)
    text = "<b>MEDIA ATTACHMENT</b>\nStep 2/3: Send a Photo or Video to attach, or click Skip."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="SKIP MEDIA", callback_data="skip_media")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PostCreatorSG.waiting_for_media)

@dp.callback_query(PostCreatorSG.waiting_for_media, F.data == "skip_media")
async def process_skip_media(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(post_media=None, media_type=None)
    await ask_for_buttons(callback.message, state)
    await callback.answer()

@dp.message(PostCreatorSG.waiting_for_media, F.photo | F.video)
async def process_post_media(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(post_media=message.photo[-1].file_id, media_type="photo")
    elif message.video:
        await state.update_data(post_media=message.video.file_id, media_type="video")
    await ask_for_buttons(message, state)

async def ask_for_buttons(message: types.Message, state: FSMContext):
    text = (
        "<b>INLINE BUTTONS</b>\nStep 3/3: Send your inline buttons format:\n\n"
        "<code>Button Text - https://example.com</code>\n"
        "<code>Second Button - https://link.com</code>\n\n"
        "Send /skip to continue without buttons."
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(PostCreatorSG.waiting_for_buttons)

@dp.message(PostCreatorSG.waiting_for_buttons, Command("skip"))
@dp.message(PostCreatorSG.waiting_for_buttons, F.text)
async def process_post_buttons(message: types.Message, state: FSMContext):
    keyboard_buttons = []
    if message.text and message.text.strip() != "/skip":
        for line in message.text.split("\n"):
            if "-" in line:
                parts = line.split("-", 1)
                keyboard_buttons.append([InlineKeyboardButton(text=parts[0].strip(), url=parts[1].strip())])

    await state.update_data(final_markup=keyboard_buttons)
    data = await state.get_data()

    await message.answer("<b>POST PREVIEW:</b>", parse_mode="HTML")
    
    text_content = data.get("post_text")
    media_id = data.get("post_media")
    media_type = data.get("media_type")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

    if media_id:
        if media_type == "photo":
            await message.answer_photo(photo=media_id, caption=text_content, reply_markup=reply_markup)
        else:
            await message.answer_video(video=media_id, caption=text_content, reply_markup=reply_markup)
    else:
        await message.answer(text_content, reply_markup=reply_markup)

    # Destination channel selection
    user_str = str(message.from_user.id)
    db = load_database()
    channels = db.get("channels", {})

    target_buttons = []
    for ch_id, ch_info in channels.items():
        if ch_info.get("added_by") == user_str or message.from_user.id == OWNER_ID:
            target_buttons.append([InlineKeyboardButton(text=ch_info["title"], callback_data=f"send_post_{ch_id}")])

    if message.from_user.id == OWNER_ID or user_str in active_admin_sessions:
        target_buttons.append([InlineKeyboardButton(text="BROADCAST TO ALL CONNECTED CHANNELS", callback_data="send_post_all")])

    target_buttons.append([InlineKeyboardButton(text="CANCEL", callback_data="main_menu")])

    if not target_buttons or len(target_buttons) == 1:
        await message.answer("You have not added any channels to post to. Use /addchannel first.")
        await state.clear()
        return

    select_kb = InlineKeyboardMarkup(inline_keyboard=target_buttons)
    await message.answer("Select destination channel to publish:", reply_markup=select_kb)

@dp.callback_query(F.data.startswith("send_post_"))
async def publish_custom_post(callback: types.CallbackQuery, state: FSMContext):
    target_key = callback.data.replace("send_post_", "")
    data = await state.get_data()
    text_content = data.get("post_text")
    media_id = data.get("post_media")
    media_type = data.get("media_type")
    keyboard_buttons = data.get("final_markup")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

    db = load_database()
    channels = db.get("channels", {})

    if target_key == "all":
        targets = list(channels.keys())
    else:
        targets = [target_key] if target_key in channels else [target_key]

    success = 0
    for target in targets:
        try:
            target_id = int(target) if target.replace("-", "").isdigit() else target
            if media_id:
                if media_type == "photo":
                    await bot.send_photo(chat_id=target_id, photo=media_id, caption=text_content, reply_markup=reply_markup)
                else:
                    await bot.send_video(chat_id=target_id, video=media_id, caption=text_content, reply_markup=reply_markup)
            else:
                await bot.send_message(chat_id=target_id, text=text_content, reply_markup=reply_markup)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.error(f"Failed to post to {target}: {e}")

    await callback.message.edit_text(f"Post successfully published to {success} channel(s).")
    await state.clear()


# --- ACCOUNT VERIFICATION ---

@dp.callback_query(F.data == "start_verification")
@dp.message(Command("verify"))
async def process_start_verification(event: types.Message | types.CallbackQuery, state: FSMContext):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = event.from_user.id

    if is_user_verified(user_id):
        text = "<b>ACCOUNT VERIFICATION PORTAL</b>\n\nYour account is verified in the Gatens Network."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="RETURN TO MAIN MENU", callback_data="main_menu")]])
        if isinstance(event, types.CallbackQuery):
            await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await event.answer()
        else:
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        return

    text = "<b>ACCOUNT VERIFICATION PORTAL</b>\nSelect the community group where you want to verify:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="CHAT GC (@chatyear)", callback_data="verify_group_chatyear"), InlineKeyboardButton(text="BUY & SELL (@fragte)", callback_data="verify_group_fragte")],
        [InlineKeyboardButton(text="MARKET HUB (@whiteages)", callback_data="verify_group_whiteages"), InlineKeyboardButton(text="CANCEL", callback_data="main_menu")]
    ])
    if isinstance(event, types.CallbackQuery):
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    await state.set_state(VerificationSG.selecting_group)

@dp.callback_query(VerificationSG.selecting_group, F.data.startswith("verify_group_"))
async def process_group_selected(callback: types.CallbackQuery, state: FSMContext):
    group_code = callback.data.split("_")[2]
    group_names = {"chatyear": "Chat GC (@chatyear)", "fragte": "Buy & Sell GC (@fragte)", "whiteages": "Market Hub (@whiteages)"}
    selected_name = group_names.get(group_code, "Selected Group")
    await state.update_data(target_group=selected_name)
    
    text = f"<b>TARGET: {selected_name}</b>\n\nStep 1/2: Upload a screenshot of your Telegram User ID or profile badge."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="CANCEL", callback_data="main_menu")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(VerificationSG.uploading_userid)
    await callback.answer()

@dp.message(VerificationSG.uploading_userid, F.photo | F.document | F.text)
async def process_userid_upload(message: types.Message, state: FSMContext):
    await state.update_data(userid_received=True)
    text = "<b>ACCOUNT VERIFICATION PORTAL</b>\n\nStep 2/2: Provide your Vouch Channel link or screenshot."
    await message.answer(text, parse_mode="HTML")
    await state.set_state(VerificationSG.uploading_vouch)

@dp.message(VerificationSG.uploading_vouch)
async def process_vouch_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_group = data.get("target_group", "General Network")
    user_id = str(message.from_user.id)
    db = load_database()
    
    if user_id not in db["users"]:
        db["users"][user_id] = {"name": message.from_user.first_name, "joined": str(message.date), "verified_chats": []}
    if "verified_chats" not in db["users"][user_id]:
        db["users"][user_id]["verified_chats"] = []
    if target_group not in db["users"][user_id]["verified_chats"]:
        db["users"][user_id]["verified_chats"].append(target_group)
    db["users"][user_id]["status"] = "verified"
    save_database(db)

    success_text = f"<b>VERIFICATION SUCCESSFUL</b>\nDestination: <b>{target_group}</b>\nStatus: <b>[VERIFIED]</b>\n\nYour record is permanently saved."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="RETURN TO MAIN MENU", callback_data="main_menu")]])
    await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# --- ADMIN COMMANDS ---

@dp.message(Command("setpass"))
async def cmd_setpass(message: types.Message, state: FSMContext):
    await message.answer("<b>Admin Registration</b>\nSend the password you want to register for admin panel authorization:", parse_mode="HTML")
    await state.set_state(AdminAuthSG.register_pass)

@dp.message(AdminAuthSG.register_pass, F.text)
async def process_register_pass(message: types.Message, state: FSMContext):
    user = message.from_user
    password = message.text.strip()
    hashed = pbkdf2_sha256.hash(password)
    db = load_database()
    db["admins"][str(user.id)] = {"username": user.username or user.first_name, "password_hash": hashed, "is_approved": 0, "role": "mod"}
    save_database(db)
    await message.answer("Password registered. Request submitted for owner review.")
    await state.clear()

@dp.message(Command("login"))
async def cmd_login(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    db = load_database()
    if user_id not in db["admins"] or db["admins"][user_id].get("is_approved", 0) == 0:
        await message.answer("You are not registered as an authorized admin.")
        return
    await message.answer("Enter your admin password:")
    await state.set_state(AdminAuthSG.login_pass)

@dp.message(AdminAuthSG.login_pass, F.text)
async def process_login_pass(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    password = message.text.strip()
    db = load_database()
    admin_data = db["admins"].get(user_id)
    if admin_data and pbkdf2_sha256.verify(password, admin_data["password_hash"]):
        active_admin_sessions.add(user_id)
        await message.answer("Login successful. Admin panel unlocked.")
    else:
        await message.answer("Invalid password.")
    await state.clear()

@dp.callback_query(F.data == "admin_panel")
@dp.message(Command("admin"))
async def process_admin_panel(event: types.Message | types.CallbackQuery):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = str(event.from_user.id)
    is_admin_authed = (event.from_user.id == OWNER_ID) or (user_id in active_admin_sessions)

    if not is_admin_authed:
        if isinstance(event, types.CallbackQuery):
            await event.answer("Unauthorized. Login required.", show_alert=True)
        else:
            await message.answer("Access denied. Please /login first.")
        return

    if isinstance(event, types.CallbackQuery):
        await event.answer()

    db = load_database()
    total_users = len(db.get("users", {}))
    verified_count = sum(1 for u in db.get("users", {}).values() if u.get("status") == "verified")
    unverified_count = total_users - verified_count

    text = f"<b>ADMIN CONTROL PANEL</b>\n• Total Users: <b>{total_users}</b>\n• Verified Users: <b>{verified_count}</b>\n• Unverified Users: <b>{unverified_count}</b>"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="MAIN MENU", callback_data="main_menu")]])

    if isinstance(event, types.CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# --- MAIN RUNNER ---
async def main():
    await start_web_server()
    if hasattr(dp, "main"):
        await dp.main()
    else:
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
