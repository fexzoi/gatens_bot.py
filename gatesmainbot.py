import asyncio
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
ADMIN_IDS = [6918967434]

# Initialize Bot and Dispatcher
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)

# Temporary in-memory storage for verification submissions (Admin Audit Panel)
PENDING_VERIFICATIONS = {}


# --- FSM STATES ---
class VerificationSG(StatesGroup):
  selecting_group = State()
  uploading_userid = State()
  uploading_vouch = State()


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


# --- FULL-WIDTH KEYBOARDS (NO EMOJIS, STYLIZED) ---


def get_join_keyboard():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="JOIN MAIN CHANNEL", url="https://t.me/+3jHzHttnfHFlZWFh"
              )
          ],
          [
              InlineKeyboardButton(
                  text="JOIN REDIRECT CHANNEL", url="https://t.me/gatens"
              )
          ],
          [
              InlineKeyboardButton(
                  text="JOIN CHAT GC", url="https://t.me/chatyear"
              )
          ],
          [
              InlineKeyboardButton(
                  text="JOIN BUY & SELL GC", url="https://t.me/fragte"
              )
          ],
          [
              InlineKeyboardButton(
                  text="JOIN MARKET HUB", url="https://t.me/whiteages"
              )
          ],
          [
              InlineKeyboardButton(
                  text="EXPLORE ECOSYSTEM BOTS", callback_data="show_bots"
              )
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
                  text="VERIFY FOR CHAT GC (@chatyear)",
                  callback_data="verify_group_chatyear",
              )
          ],
          [
              InlineKeyboardButton(
                  text="VERIFY FOR BUY & SELL GC (@fragte)",
                  callback_data="verify_group_fragte",
              )
          ],
          [
              InlineKeyboardButton(
                  text="VERIFY FOR MARKET HUB (@whiteages)",
                  callback_data="verify_group_whiteages",
              )
          ],
          [
              InlineKeyboardButton(
                  text="« BACK TO MAIN MENU", callback_data="main_menu"
              )
          ],
      ]
  )


def get_main_menu_keyboard(is_admin: bool):
  buttons = [
      [
          InlineKeyboardButton(
              text="START ACCOUNT VERIFICATION", callback_data="start_verification"
          )
      ],
      [
          InlineKeyboardButton(
              text="VIEW NETWORK DESTINATIONS", callback_data="view_hubs"
          )
      ],
  ]
  if is_admin:
    buttons.append([
        InlineKeyboardButton(
            text="[ADMIN PANEL] AUDIT SUBMISSIONS", callback_data="admin_panel"
        )
    ])
  return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- HANDLERS: START & MAIN MENU ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
  await state.clear()
  user_id = message.from_user.id
  user_name = message.from_user.first_name
  is_admin = user_id in ADMIN_IDS

  text = (
      f"<b><u>GATENS NETWORK INFRASTRUCTURE</u></b>\n"
      f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f"USER: <code>{user_name}</code>\n\n"
      f"<b>MANDATORY INSTRUCTION:</b>\n"
      f"You must <u>verify your account</u> in the Gatens Network before interacting with community groups and markets.\n\n"
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
  user_id = callback.from_user.id
  is_admin = user_id in ADMIN_IDS

  text = (
      "<b><u>GATENS NETWORK HUB</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "Select an action below:"
  )
  await callback.message.edit_text(
      text, reply_markup=get_main_menu_keyboard(is_admin), parse_mode="HTML"
  )
  await callback.answer()


@dp.callback_query(F.data == "view_hubs")
async def process_view_hubs(callback: types.CallbackQuery):
  text = (
      "<b><u>OFFICIAL NETWORK HUBS & CHANNELS</u></b>\n"
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
      "<b><u>GATENS ECOSYSTEM BOTS</u></b>\n"
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


# --- VERIFICATION WORKFLOW (FSM) ---


@dp.callback_query(F.data == "start_verification")
async def process_start_verification(
    callback: types.CallbackQuery, state: FSMContext
):
  text = (
      "<b><u>ACCOUNT VERIFICATION PORTAL</u></b>\n"
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
      f"<b><u>TARGET: {selected_name}</u></b>\n"
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
  # Store reference to User ID proof
  await state.update_data(userid_msg=message)

  text = (
      "<b><u>ACCOUNT VERIFICATION PORTAL</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "<b>STEP 2/2: VOUCH CHANNEL PROOF</b>\n\n"
      "User ID received successfully.\n\n"
      "Now, provide your <u>Vouch Channel link</u> or upload a screenshot of your reputation history."
  )
  await message.answer(text, parse_mode="HTML")
  await state.set_state(VerificationSG.uploading_vouch)


@dp.message(VerificationSG.uploading_vouch)
async def process_vouch_upload(message: types.Message, state: FSMContext):
  data = await state.get_data()
  target_group = data.get("target_group", "General Network")
  user_id = message.from_user.id
  username = message.from_user.username or "No Username"

  # Save to Pending Verifications dict for Admin Review
  if user_id not in PENDING_VERIFICATIONS:
    PENDING_VERIFICATIONS[user_id] = []
  PENDING_VERIFICATIONS[user_id].append({
      "group": target_group,
      "username": username,
      "vouch_info": message.text or "[Media Proof]",
  })

  success_text = (
      "<b><u>VERIFICATION SUBMITTED SUCCESSFULLY</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f"Target Destination: <b>{target_group}</b>\n"
      "Status: <code>PENDING ADMIN AUDIT</code>\n\n"
      "Your verification files have been recorded and sent to the network administration panel."
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


# --- ADMIN PANEL LOGIC ---


@dp.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback: types.CallbackQuery):
  if callback.from_user.id not in ADMIN_IDS:
    await callback.answer("Unauthorized action.", show_alert=True)
    return

  total_pending = sum(len(v) for v in PENDING_VERIFICATIONS.values())

  text = (
      "<b><u>ADMIN CONTROL PANEL</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      f"• Total Pending Verifications: <b>{total_pending}</b>\n"
      f"• System Status: <code>100% OPERATIONAL</code>\n\n"
      "Select an action below:"
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="VIEW PENDING SUBMISSIONS",
                  callback_data="admin_view_pending",
              )
          ],
          [
              InlineKeyboardButton(
                  text="« RETURN TO MAIN MENU", callback_data="main_menu"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


@dp.callback_query(F.data == "admin_view_pending")
async def process_admin_view_pending(callback: types.CallbackQuery):
  if callback.from_user.id not in ADMIN_IDS:
    await callback.answer("Unauthorized action.", show_alert=True)
    return

  if not PENDING_VERIFICATIONS:
    text = (
        "<b><u>PENDING VERIFICATIONS</u></b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "No pending user submissions found in the queue."
    )
  else:
    text = (
        "<b><u>PENDING VERIFICATIONS QUEUE</u></b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for uid, submissions in PENDING_VERIFICATIONS.items():
      for sub in submissions:
        text += (
            f"• User ID: <code>{uid}</code> (@{sub['username']})\n"
            f"  Target: <b>{sub['group']}</b>\n"
            f"  Vouch Data: {sub['vouch_info']}\n\n"
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


# --- GROUP CHAT COMMANDS & /VERIFY ---


@dp.message(Command("verify"))
async def cmd_verify_command(message: types.Message, state: FSMContext):
  text = (
      "<b><u>SECURE GROUP VERIFICATION</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "Select your target destination group to begin verification:"
  )
  await message.answer(
      text, reply_markup=get_group_selection_keyboard(), parse_mode="HTML"
  )


@dp.message(Command("network"))
async def cmd_network_info(message: types.Message):
  text = (
      "<b><u>GATENS NETWORK DIRECTORY</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "• Main Announcement: Check pinned message\n"
      "• Support Portal: <code>@gatens</code>\n"
      "• Status: Operational"
  )
  await message.answer(text, parse_mode="HTML")


@dp.message(Command("reputation"))
async def cmd_reputation_info(message: types.Message):
  text = (
      "<b><u>REPUTATION & SECURITY GUIDELINES</u></b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
      "Always verify user IDs through <code>@gatens_bot</code> before conducting deals."
  )
  await message.answer(text, parse_mode="HTML")


@dp.message(Command("rules"))
async def cmd_group_rules(message: types.Message):
  text = (
      "<b><u>COMMUNITY CONDUCT RULES</u></b>\n"
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
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
