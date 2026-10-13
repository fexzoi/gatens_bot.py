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


# --- DUMMY WEB SERVER ---
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
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="MAIN CHANNEL", url="https://t.me/+3jHzHttnfHFlZWFh"), InlineKeyboardButton(text="REDIRECT CH", url="https://t.me/gatens")],
        [InlineKeyboardButton(text="CHAT GC", url="https://t.me/chatyear"), InlineKeyboardButton(text="BUY & SELL", url="https://t.me/fragte")],
        [InlineKeyboardButton(text="MARKET HUB", url="https://t.me/whiteages"), InlineKeyboardButton(text="OTHER BOTS", callback_data="show_bots")],
        [InlineKeyboardButton(text="« BACK TO MAIN MENU", callback_data="main_menu")]
    ])

def get_group_selection_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="CHAT GC (@chatyear)", callback_data="verify_group_chatyear"), InlineKeyboardButton(text="BUY & SELL (@fragte)", callback_data="verify_group_fragte")],
        [InlineKeyboardButton(text="MARKET HUB (@whiteages)", callback_data="verify_group_whiteages"), InlineKeyboardButton(text="« CANCEL", callback_data="main_menu")]
    ])

def get_main_menu_keyboard(is_admin: bool):
    buttons = [
        [InlineKeyboardButton(text="VERIFY ACCOUNT", callback_data="start_verification"), InlineKeyboardButton(text="NETWORK HUBS", callback_data="view_hubs")],
        [InlineKeyboardButton(text="📝 CREATE POST", callback_data="start_create_post")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="[ADMIN PANEL]", callback_data="admin_panel"), InlineKeyboardButton(text="BROADCAST", callback_data="admin_broadcast")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- AUTO-DISCOVER CHATS ---
@dp.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def auto_track_network_chats(message: types.Message):
    chat = message.chat
    db = load_database()
    chat_id_str = str(chat.id)
    if chat_id_str not in db["broadcast_targets"]:
        db["broadcast_targets"][chat_id_str] = {"title": chat.title or "Unnamed Chat", "type": chat.type}
        save_database(db)


# --- HANDLERS: START & MAIN MENU ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    is_admin = (message.from_user.id in [OWNER_ID]) or (user_id in active_admin_sessions)

    db = load_database()
    if user_id not in db["users"]:
        db["users"][user_id] = {"name": user_name, "joined": str(message.date), "status": "unverified", "verified_chats": []}
        save_database(db)

    if "verified_chats" not in db["users"][user_id]:
        db["users"][user_id]["verified_chats"] = []
        save_database(db)

    status_label = db["users"][user_id]["status"].upper()
    text = f"<b>GATENS NETWORK INFRASTRUCTURE</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nUSER: <code>{user_name}</code>\nSTATUS: <b>[{status_label}]</b>\n\n<b>MANDATORY INSTRUCTION:</b>\nYou must verify your account in the Gatens Network before interacting with community groups and markets.\n\nSelect an option below to proceed:"
    await message.answer(text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML")

@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = str(callback.from_user.id)
    is_admin = (callback.from_user.id in [OWNER_ID]) or (user_id in active_admin_sessions)
    db = load_database()
    status_label = db.get("users", {}).get(user_id, {}).get("status", "unverified").upper()
    text = f"<b>GATENS NETWORK HUB</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSTATUS: <b>[{status_label}]</b>\nSelect an action below:"
    await callback.message.edit_text(text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "view_hubs")
async def process_view_hubs(callback: types.CallbackQuery):
    text = "<b>OFFICIAL NETWORK HUBS & CHANNELS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nAccess our verified channels, community groups, and markets below:"
    await callback.message.edit_text(text, reply_markup=get_join_keyboard(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "show_bots")
async def process_show_bots(callback: types.CallbackQuery):
    text = "<b>GATENS ECOSYSTEM BOTS</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n• Core Infrastructure Bot: <code>@gatens_bot</code>\n• More specialized network utilities coming online."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« BACK TO DESTINATIONS", callback_data="view_hubs")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# --- ADMIN LOGIN SYSTEM ---
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
    db["admins"][str(user.id)] = {"username": user.username or user.first_name, "password_hash": hashed, "is_approved": 0, "role": "mod"}
    save_database(db)
    await message.answer("✅ Password registered! Your request has been sent to the Owner for approval.")
    await state.clear()
    approval_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Approve", callback_data=f"apprv_{user.id}"), InlineKeyboardButton(text="❌ Reject", callback_data=f"rej_{user.id}")]])
    try:
        await bot.send_message(chat_id=OWNER_ID, text=f"🔔 **New Admin Registration Request**\nUser: @{user.username or 'No Username'}\nID: `{user.id}`", parse_mode="HTML", reply_markup=approval_keyboard)
    except Exception as e:
        logging.error(f"Failed to notify owner: {e}")

@dp.callback_query(F.data.startswith("apprv_") | F.data.startswith("rej_"))
async def process_admin_approval_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Unauthorized.", show_alert=True)
        return
    parts = callback.data.split("_")
    action = parts[0]
    target_id = parts[1]
    db = load_database()
    if target_id in db["admins"]:
        if action == "apprv":
            db["admins"][target_id]["is_approved"] = 1
            save_database(db)
            await callback.message.edit_text(f"✅ Admin ID `{target_id}` has been **APPROVED**.")
            try:
                await bot.send_message(chat_id=int(target_id), text="🎉 Your admin request was **APPROVED** by the Owner! You can now use `/login`.")
            except:
                pass
        else:
            del db["admins"][target_id]
            save_database(db)
            await callback.message.edit_text(f"❌ Admin ID `{target_id}` was rejected.")
    else:
        await callback.message.edit_text("⚠️ Admin record not found.")
    await callback.answer()

@dp.message(Command("login"))
async def cmd_login(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    db = load_database()
    if user_id not in db["admins"] or db["admins"][user_id].get("is_approved", 0) == 0:
        await message.answer("🚫 You are not registered or your request is still pending owner approval.")
        return
    await message.answer("🔐 Enter your custom admin password to log in:")
    await state.set_state(AdminAuthSG.login_pass)

@dp.message(AdminAuthSG.login_pass, F.text)
async def process_login_pass(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    password = message.text.strip()
    db = load_database()
    admin_data = db["admins"].get(user_id)
    if admin_data and pbkdf2_sha256.verify(password, admin_data["password_hash"]):
        active_admin_sessions.add(user_id)
        await message.answer("✅ **Login Successful!** You now have full access to `/admin` commands.")
    else:
        await message.answer("❌ **Invalid Password.** Access denied.")
    await state.clear()


# --- POST CREATOR ---
@dp.callback_query(F.data == "start_create_post")
@dp.message(Command("createpost"))
async def cmd_create_post(event: types.Message | types.CallbackQuery, state: FSMContext):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    if isinstance(event, types.CallbackQuery):
        await event.answer()
    text = "📝 **CONTROLLER POST CREATOR**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSend me the text or caption content for your post:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« CANCEL", callback_data="main_menu")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PostCreatorSG.waiting_for_text)

@dp.message(PostCreatorSG.waiting_for_text, F.text)
async def process_post_text(message: types.Message, state: FSMContext):
    await state.update_data(post_text=message.text)
    text = "📸 **STEP 2/3: MEDIA ATTACHMENT**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSend a Photo or Video to attach, or click Skip to send text only."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="SKIP MEDIA ⏭️", callback_data="skip_media")]])
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PostCreatorSG.waiting_for_media)

@dp.callback_query(PostCreatorSG.waiting_for_media, F.data == "skip_media")
async def process_skip_media(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(post_media=None, media_type=None)
    await ask_for_buttons(callback.message)
    await callback.answer()

@dp.message(PostCreatorSG.waiting_for_media, F.photo | F.video)
async def process_post_media(message: types.Message, state: FSMContext):
    if message.photo:
        await state.update_data(post_media=message.photo[-1].file_id, media_type="photo")
    elif message.video:
        await state.update_data(post_media=message.video.file_id, media_type="video")
    await ask_for_buttons(message)

async def ask_for_buttons(message: types.Message):
    text = "🔗 **STEP 3/3: INLINE BUTTONS**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSend your inline buttons format:\n<code>Button Text - https://link.com</code>\n*(Each button on a new line)*\n\nOr type /skip to proceed without buttons."
    await message.answer(text, parse_mode="HTML")
    await PostCreatorSG.waiting_for_buttons # state transition managed via handlers

@dp.message(PostCreatorSG.waiting_for_buttons, Command("skip"))
@dp.message(PostCreatorSG.waiting_for_buttons, F.text)
async def process_post_buttons(message: types.Message, state: FSMContext):
    keyboard_buttons = []
    if message.text and message.text.strip() != "/skip":
        for line in message.text.split("\n"):
            if "-" in line:
                parts = line.split("-", 1)
                keyboard_buttons.append([InlineKeyboardButton(text=parts[0].strip(), url=parts[1].strip())])

    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None
    data = await state.get_data()
    await message.answer("👀 **POST PREVIEW:**", parse_mode="HTML")
    
    text_content = data.get("post_text")
    media_id = data.get("post_media")
    media_type = data.get("media_type")

    if media_id:
        if media_type == "photo":
            await message.answer_photo(photo=media_id, caption=text_content, reply_markup=reply_markup)
        else:
            await message.answer_video(video=media_id, caption=text_content, reply_markup=reply_markup)
    else:
        await message.answer(text_content, reply_markup=reply_markup)

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📢 PUBLISH / BROADCAST", callback_data="publish_custom_post"), InlineKeyboardButton(text="❌ CANCEL", callback_data="main_menu")]])
    await state.update_data(final_markup=keyboard_buttons)
    await message.answer("Ready to send? Choose below:", reply_markup=confirm_kb)

@dp.callback_query(F.data == "publish_custom_post")
async def publish_custom_post(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text_content = data.get("post_text")
    media_id = data.get("post_media")
    media_type = data.get("media_type")
    keyboard_buttons = data.get("final_markup")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons) if keyboard_buttons else None

    db = load_database()
    discovered_chats = list(db.get("broadcast_targets", {}).keys())
    default_chats = ["@chatyear", "@fragte", "@whiteages", "@gatens"]
    targets = list(set(discovered_chats + default_chats))

    success = 0
    for target in targets:
        try:
            if media_id:
                if media_type == "photo":
                    await bot.send_photo(chat_id=target, photo=media_id, caption=text_content, reply_markup=reply_markup)
                else:
                    await bot.send_video(chat_id=target, video=media_id, caption=text_content, reply_markup=reply_markup)
            else:
                await bot.send_message(chat_id=target, text=text_content, reply_markup=reply_markup)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await callback.message.edit_text(f"✅ **Post successfully published to {success} network channels/groups!**")
    await state.clear()


# --- VERIFICATION ---
@dp.callback_query(F.data == "start_verification")
async def process_start_verification(callback: types.CallbackQuery, state: FSMContext):
    text = "<b>ACCOUNT VERIFICATION PORTAL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSelect the specific community group or market where you want to complete your verification record:"
    await callback.message.edit_text(text, reply_markup=get_group_selection_keyboard(), parse_mode="HTML")
    await state.set_state(VerificationSG.selecting_group)
    await callback.answer()

@dp.callback_query(VerificationSG.selecting_group, F.data.startswith("verify_group_"))
async def process_group_selected(callback: types.CallbackQuery, state: FSMContext):
    group_code = callback.data.split("_")[2]
    group_names = {"chatyear": "Chat GC (@chatyear)", "fragte": "Buy & Sell GC (@fragte)", "whiteages": "Market Hub (@whiteages)"}
    selected_name = group_names.get(group_code, "Selected Group")
    await state.update_data(target_group=selected_name)
    text = f"<b>TARGET: {selected_name}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<b>STEP 1/2: USER ID PROOF SUBMISSION</b>\n\nPlease send or upload a clean screenshot of your Telegram User ID or profile badge."
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« CANCEL & RETURN", callback_data="main_menu")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(VerificationSG.uploading_userid)
    await callback.answer()

@dp.message(VerificationSG.uploading_userid, F.photo | F.document | F.text)
async def process_userid_upload(message: types.Message, state: FSMContext):
    await state.update_data(userid_received=True)
    text = "<b>ACCOUNT VERIFICATION PORTAL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<b>STEP 2/2: VOUCH CHANNEL PROOF</b>\n\nUser ID received successfully.\n\nNow, provide your Vouch Channel link or upload a screenshot of your reputation history."
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
    success_text = f"<b>VERIFICATION SUCCESSFUL (AUTO-APPROVED)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nTarget Destination: <b>{target_group}</b>\nStatus: <code>[VERIFIED]</code>\n\nYour account has been verified and registered for this section!"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« RETURN TO MAIN MENU", callback_data="main_menu")]])
    await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# --- ADMIN PANEL & BROADCAST ---
@dp.callback_query(F.data == "admin_panel")
@dp.message(Command("admin"))
async def process_admin_panel(event: types.Message | types.CallbackQuery):
    message = event.message if isinstance(event, types.CallbackQuery) else event
    user_id = str(event.from_user.id)
    is_admin_authed = (event.from_user.id in [OWNER_ID]) or (user_id in active_admin_sessions)
    if not is_admin_authed:
        if isinstance(event, types.CallbackQuery):
            await event.answer("🔒 Unauthorized. Please /login first.", show_alert=True)
        else:
            await message.answer("🔒 **Access Denied.** Please `/login` with your authorized admin password.")
        return
    if isinstance(event, types.CallbackQuery):
        await event.answer()
    db = load_database()
    total_users = len(db.get("users", {}))
    verified_count = sum(1 for u in db.get("users", {}).values() if u.get("status") == "verified")
    unverified_count = total_users - verified_count
    text = f"<b>ADMIN CONTROL PANEL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n• Total Users: <b>{total_users}</b>\n• Verified Users: <b>{verified_count}</b>\n• Unverified Users: <b>{unverified_count}</b>\n\nManage database records below:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="VERIFIED USERS", callback_data="admin_list_verified"), InlineKeyboardButton(text="UNVERIFIED USERS", callback_data="admin_list_unverified")],
        [InlineKeyboardButton(text="« MAIN MENU", callback_data="main_menu")]
    ])
    if isinstance(event, types.CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@dp.callback_query(F.data == "admin_broadcast")
async def process_admin_broadcast_prompt(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    if (callback.from_user.id not in [OWNER_ID]) and (user_id not in active_admin_sessions):
        await callback.answer("Unauthorized action.", show_alert=True)
        return
    text = "<b>BROADCAST MESSAGE PORTAL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nSelect the target audience for your broadcast:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ALL USERS", callback_data="bc_target_users"), InlineKeyboardButton(text="ALL DISCOVERED HUBS/GCs", callback_data="bc_target_groups")],
        [InlineKeyboardButton(text="« CANCEL", callback_data="admin_panel")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(BroadcastSG.choosing_target)
    await callback.answer()

@dp.callback_query(BroadcastSG.choosing_target, F.data.startswith("bc_target_"))
async def process_bc_target_selected(callback: types.CallbackQuery, state: FSMContext):
    target_type = callback.data.split("_")[2]
    await state.update_data(target_type=target_type)
    target_name = "Registered Bot Users" if target_type == "users" else "Discovered Network Chat Groups & Hubs"
    text = f"<b>BROADCAST MESSAGE PORTAL</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nTarget: <b>{target_name}</b>\n\nNow, send the text, announcement, or media message you want to broadcast:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« BACK", callback_data="admin_broadcast")]])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(BroadcastSG.waiting_for_message)
    await callback.answer()

@dp.message(BroadcastSG.waiting_for_message)
async def execute_broadcast(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    if (message.from_user.id not in [OWNER_ID]) and (user_id not in active_admin_sessions):
        return
    data = await state.get_data()
    target_type = data.get("target_type", "users")
    status_msg = await message.answer("<b>Broadcasting message... Please wait.</b>", parse_mode="HTML")
    success_count = 0
    fail_count = 0
    db = load_database()
    if target_type == "users":
        targets = list(db.get("users", {}).keys())
    else:
        discovered_chats = list(db.get("broadcast_targets", {}).keys())
        default_chats = ["@chatyear", "@fragte", "@whiteages", "@gatens"]
        targets = list(set(discovered_chats + default_chats))
    for target in targets:
        try:
            await message.copy_to(chat_id=target)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1
    report = f"<b>BROADCAST COMPLETED</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n• Target Audience: <b>{target_type.upper()}</b>\n• Successfully Delivered: <b>{success_count}</b>\n• Failed / Blocked: <b>{fail_count}</b>"
    await status_msg.edit_text(report, parse_mode="HTML")
    await state.clear()


# --- NETWORK COMMANDS ---
@dp.message(Command("network"))
async def cmd_network_info(message: types.Message):
    text = "<b>GATENS NETWORK DIRECTORY</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n• Main Announcement: Check pinned message\n• Support Portal: <code>@gatens</code>\n• Status: Operational"
    await message.answer(text, parse_mode="HTML")


# --- MAIN RUNNER ---
async def main():
    print("Starting web server for 24/7 uptime...")
    await start_web_server()
    print("Starting @gatens_bot polling...")
    if hasattr(dp, "main"):
        await dp.main()
    else:
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
