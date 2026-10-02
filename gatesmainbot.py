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

# Configured credentials
TOKEN = os.getenv("BOT_TOKEN", "8841797167:AAGqfC5laKal7Z7D_Q_PVDQJa7sQRri9BIY")
ADMIN_IDS = [8480522053]

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
    return {"verifications": {}, "users": {}}


def save_database(data):
    try:
        with open(DB_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Failed to save database: {e}")


# --- FSM STATES ---
class VerificationSG(StatesGroup):
    selecting_group = State()
    uploading_userid = State()
    uploading_vouch = State()


class BroadcastSG(StatesGroup):
    choosing_target = State()
    waiting_for_message = State()


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


# --- SIDE-BY-SIDE DUAL KEYBOARDS ---


def get_join_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="MAIN CHANNEL", url="https://t.me/+3jHzHttnfHFlZWFh"
                ),
                InlineKeyboardButton(
                    text="REDIRECT CH", url="https://t.me/gatens"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="CHAT GC", url="https://t.me/chatyear"
                ),
                InlineKeyboardButton(
                    text="BUY & SELL", url="https://t.me/fragte"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="MARKET HUB", url="https://t.me/whiteages"
                ),
                InlineKeyboardButton(
                    text="OTHER BOTS", callback_data="show_bots"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="« BACK TO MAIN MENU", callback_data="main_menu"
                )
            ],
        ]
    )


def get_group_selection_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="CHAT GC (@chatyear)",
                    callback_data="verify_group_chatyear",
                ),
                InlineKeyboardButton(
                    text="BUY & SELL (@fragte)",
                    callback_data="verify_group_fragte",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="MARKET HUB (@whiteages)",
                    callback_data="verify_group_whiteages",
                ),
                InlineKeyboardButton(
                    text="« CANCEL", callback_data="main_menu"
                ),
            ],
        ]
    )


def get_main_menu_keyboard(is_admin: bool):
    buttons = [
        [
            InlineKeyboardButton(
                text="VERIFY ACCOUNT", callback_data="start_verification"
            ),
            InlineKeyboardButton(
                text="NETWORK HUBS", callback_data="view_hubs"
            ),
        ]
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(
                text="[ADMIN PANEL]", callback_data="admin_panel"
            ),
            InlineKeyboardButton(text="BROADCAST", callback_data="admin_broadcast"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- HANDLERS: START & MAIN MENU ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    user_name = message.from_user.first_name
    is_admin = int(user_id) in ADMIN_IDS

    db = load_database()
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": user_name,
            "joined": str(message.date),
            "status": "unverified",
            "verified_chats": [],
        }
        save_database(db)

    # Ensure 'verified_chats' exists for older users in DB
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
    is_admin = int(user_id) in ADMIN_IDS

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
            InlineKeyboardButton(
                text="« BACK TO DESTINATIONS", callback_data="view_hubs"
            )
        ]]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


# --- VERIFICATION WORKFLOW & AUTO CHAT DETECTION ---


@dp.callback_query(F.data == "start_verification")
async def process_start_verification(
    callback: types.CallbackQuery, state: FSMContext
):
    text = (
        "<b>ACCOUNT VERIFICATION PORTAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the specific community group or market where you want to complete your verification record:"
    )
    await callback.message.edit_text(
        text, reply_markup=get_group_selection_keyboard(), parse_mode="HTML"
    )
    await state.set_state(VerificationSG.selecting_group)
    await callback.answer()


@dp.callback_query(
    VerificationSG.selecting_group, F.data.startswith("verify_group_")
)
async def process_group_selected(
    callback: types.CallbackQuery, state: FSMContext
):
    group_code = callback.data.split("_")[2]
    group_names = {
        "chatyear": "Chat GC (@chatyear)",
        "fragte": "Buy & Sell GC (@fragte)",
        "whiteages": "Market Hub (@whiteages)",
    }
    selected_name = group_names.get(group_code, "Selected Group")
    await state.update_data(target_group=selected_name)

    text = (
        f"<b>TARGET: {selected_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>STEP 1/2: USER ID PROOF SUBMISSION</b>\n\n"
        f"Please send or upload a clean screenshot of your Telegram User ID or profile badge."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="« CANCEL & RETURN", callback_data="main_menu"
            )
        ]]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await state.set_state(VerificationSG.uploading_userid)
    await callback.answer()


@dp.message(VerificationSG.uploading_userid, F.photo | F.document | F.text)
async def process_userid_upload(message: types.Message, state: FSMContext):
    await state.update_data(userid_received=True)

    text = (
        "<b>ACCOUNT VERIFICATION PORTAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>STEP 2/2: VOUCH CHANNEL PROOF</b>\n\n"
        "User ID received successfully.\n\n"
        "Now, provide your Vouch Channel link or upload a screenshot of your reputation history."
    )
    await message.answer(text, parse_mode="HTML")
    await state.set_state(VerificationSG.uploading_vouch)


@dp.message(VerificationSG.uploading_vouch)
async def process_vouch_upload(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_group = data.get("target_group", "General Network")
    user_id = str(message.from_user.id)

    db = load_database()

    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": message.from_user.first_name,
            "joined": str(message.date),
            "verified_chats": [],
        }

    if "verified_chats" not in db["users"][user_id]:
        db["users"][user_id]["verified_chats"] = []

    # Save target group into user's verified list if not already there
    if target_group not in db["users"][user_id]["verified_chats"]:
        db["users"][user_id]["verified_chats"].append(target_group)

    db["users"][user_id]["status"] = "verified"
    save_database(db)

    success_text = (
        "<b>VERIFICATION SUCCESSFUL (AUTO-APPROVED)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Target Destination: <b>{target_group}</b>\n"
        "Status: <code>[VERIFIED]</code>\n\n"
        "Your account has been verified and registered for this section!"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="« RETURN TO MAIN MENU", callback_data="main_menu"
            )
        ]]
    )
    await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


# --- AUTOMATIC GROUP VERIFICATION VIA /verify COMMAND IN GCS ---


@dp.message(Command("verify", "verification"))
async def cmd_verify_command(message: types.Message, state: FSMContext):
    chat = message.chat

    # If command is used inside a Group, Supergroup, or Channel GC
    if chat.type in ["group", "supergroup"]:
        chat_title = chat.title
        lower_title = chat_title.lower()

        # Bot automatically understands where the user is verifying based on group title keywords
        if "buy" in lower_title or "sell" in lower_title:
            section_type = f"Buy/Sell Group: {chat_title}"
        elif "market" in lower_title:
            section_type = f"Market GC: {chat_title}"
        else:
            section_type = f"Chat GC: {chat_title}"

        user_id = str(message.from_user.id)
        db = load_database()

        if user_id not in db["users"]:
            db["users"][user_id] = {
                "name": message.from_user.first_name,
                "joined": str(message.date),
                "status": "verified",
                "verified_chats": [],
            }

        if "verified_chats" not in db["users"][user_id]:
            db["users"][user_id]["verified_chats"] = []

        if section_type not in db["users"][user_id]["verified_chats"]:
            db["users"][user_id]["verified_chats"].append(section_type)

        db["users"][user_id]["status"] = "verified"
        save_database(db)

        text = (
            f"<b>GROUP VERIFICATION SUCCESSFUL</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Detected Location: <b>{chat_title}</b>\n"
            f"Status: <code>[VERIFIED]</code>\n\n"
            f"You are now registered for this group session."
        )
        await message.answer(text, parse_mode="HTML")
    else:
        # Fallback to menu if used in Bot PM
        text = (
            "<b>SECURE GROUP VERIFICATION</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select your target destination group to begin verification:"
        )
        await message.answer(
            text, reply_markup=get_group_selection_keyboard(), parse_mode="HTML"
        )


# --- CHECKER COMMANDS SHOWING SPECIFIC VERIFIED GROUP NAMES ---


@dp.message(Command("status", "check"))
async def cmd_check_status(message: types.Message):
    target_user = message.from_user
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user

    user_id = str(target_user.id)
    db = load_database()

    user_info = db.get("users", {}).get(user_id, {"status": "unverified", "verified_chats": []})
    status = user_info.get("status", "unverified").upper()
    verified_chats = user_info.get("verified_chats", [])

    chats_text = "\n".join([f"• {gc}" for gc in verified_chats]) if verified_chats else "• No specific groups verified yet."

    text = (
        f"<b>USER STATUS CHECKER</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"User: <code>{target_user.first_name}</code>\n"
        f"ID: <code>{user_id}</code>\n"
        f"Overall Status: <b>[{status}]</b>\n\n"
        f"<b>Verified Group Records:</b>\n{chats_text}"
    )
    await message.reply(text, parse_mode="HTML")


# --- FULL ADMIN PANEL LOGIC ---


@dp.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Unauthorized action.", show_alert=True)
        return

    db = load_database()
    total_users = len(db.get("users", {}))
    verified_count = sum(
        1 for u in db.get("users", {}).values() if u.get("status") == "verified"
    )
    unverified_count = total_users - verified_count

    text = (
        "<b>ADMIN CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Total Users: <b>{total_users}</b>\n"
        f"• Verified Users: <b>{verified_count}</b>\n"
        f"• Unverified Users: <b>{unverified_count}</b>\n\n"
        "Manage database records below:"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="VERIFIED USERS", callback_data="admin_list_verified"
                ),
                InlineKeyboardButton(
                    text="UNVERIFIED USERS", callback_data="admin_list_unverified"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="« MAIN MENU", callback_data="main_menu"
                )
            ],
        ]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"admin_list_verified", "admin_list_unverified"}))
async def process_admin_list_users(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Unauthorized action.", show_alert=True)
        return

    target_status = (
        "verified" if callback.data == "admin_list_verified" else "unverified"
    )
    db = load_database()
    users = db.get("users", {})

    filtered = [
        (uid, info)
        for uid, info in users.items()
        if info.get("status") == target_status
    ]

    text = (
        f"<b>USER LIST: {target_status.upper()}</b>"
        "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    if not filtered:
        text += "No records found in this category."
    else:
        for uid, info in filtered[:10]:
            text += (
                f"• <code>{uid}</code> | {info['name']} | Status: <b>{info['status']}</b>\n"
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="« BACK TO ADMIN PANEL", callback_data="admin_panel"
            )
        ]]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await callback.answer()


# --- BROADCAST SYSTEM ---


@dp.callback_query(F.data == "admin_broadcast")
async def process_admin_broadcast_prompt(
    callback: types.CallbackQuery, state: FSMContext
):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("Unauthorized action.", show_alert=True)
        return

    text = (
        "<b>BROADCAST MESSAGE PORTAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select the target audience for your broadcast:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ALL USERS", callback_data="bc_target_users"
                ),
                InlineKeyboardButton(
                    text="ALL CHAT GROUPS / HUBS",
                    callback_data="bc_target_groups",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="« CANCEL", callback_data="admin_panel"
                )
            ],
        ]
    )
    await callback.message.edit_text(
        text, reply_markup=keyboard, parse_mode="HTML"
    )
    await state.set_state(BroadcastSG.choosing_target)
    await callback.answer()


@dp.callback_query(
    BroadcastSG.choosing_target, F.data.startswith("bc_target_")
)
async def process_bc_target_selected(
    callback: types.CallbackQuery, state: FSMContext
):
    target_type = callback.data.split("_")[2]
    await state.update_data(target_type=target_type)

    target_name = (
        "Registered Bot Users"
        if target_type == "users"
        else "Network Chat Groups & Hubs"
    )

    text = (
        "<b>BROADCAST MESSAGE PORTAL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Target: <b>{target_name}</b>\n\n"
        "Now, send the text, announcement, or media message you want to broadcast:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="« BACK", callback_data="admin_broadcast")
        ]]
    )
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(BroadcastSG.waiting_for_message)
    await callback.answer()


@dp.message(BroadcastSG.waiting_for_message)
async def execute_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    data = await state.get_data()
    target_type = data.get("target_type", "users")

    status_msg = await message.answer(
        "<b>Broadcasting message... Please wait.</b>", parse_mode="HTML"
    )

    success_count = 0
    fail_count = 0

    if target_type == "users":
        db = load_database()
        targets = list(db.get("users", {}).keys())
    else:
        targets = ["@chatyear", "@fragte", "@whiteages", "@gatens"]

    for target in targets:
        try:
            await message.copy_to(chat_id=target)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            fail_count += 1

    report = (
        "<b>BROADCAST COMPLETED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Target Audience: <b>{target_type.upper()}</b>\n"
        f"• Successfully Delivered: <b>{success_count}</b>\n"
        f"• Failed / Blocked: <b>{fail_count}</b>"
    )
    await status_msg.edit_text(report, parse_mode="HTML")
    await state.clear()


# --- GENERAL NETWORK COMMANDS ---


@dp.message(Command("network"))
async def cmd_network_info(message: types.Message):
    text = (
        "<b>GATENS NETWORK DIRECTORY</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "• Main Announcement: Check pinned message\n"
        "• Support Portal: <code>@gatens</code>\n"
        "• Status: Operational"
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("reputation"))
async def cmd_reputation_info(message: types.Message):
    text = (
        "<b>REPUTATION & SECURITY GUIDELINES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Always verify user IDs through <code>@gatens_bot</code> before conducting deals."
    )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("rules"))
async def cmd_group_rules(message: types.Message):
    text = (
        "<b>COMMUNITY CONDUCT RULES</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "1. Respect all network participants.\n"
        "2. Zero tolerance for scam or unverified links.\n"
        "3. Conduct all transactions through official channels."
    )
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
