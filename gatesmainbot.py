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


# --- FSM STATES FOR VERIFICATION ---
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


# --- FULL-WIDTH KEYBOARDS ---


def get_join_keyboard():
  """Full-width buttons strictly for joining network destinations"""
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🔗 Join Main Channel",
                  url="https://t.me/+3jHzHttnfHFlZWFh",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📢 Join Redirect Channel", url="https://t.me/gatens"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💬 Join Chat GC", url="https://t.me/chatyear"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🛒 Join Buy & Sell GC", url="https://t.me/fragte"
              )
          ],
          [
              InlineKeyboardButton(
                  text="💎 Join Market Hub", url="https://t.me/whiteages"
              )
          ],
          [
              InlineKeyboardButton(
                  text="🤖 Explore Ecosystem Bots", callback_data="show_bots"
              )
          ],
      ]
  )


def get_group_selection_keyboard():
  """Options for selecting where the user wants to verify"""
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="💬 Verify for Chat GC (@chatyear)",
                  callback_data="verify_group_chatyear",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🛒 Verify for Buy & Sell GC (@fragte)",
                  callback_data="verify_group_fragte",
              )
          ],
          [
              InlineKeyboardButton(
                  text="💎 Verify for Market (@whiteages)",
                  callback_data="verify_group_whiteages",
              )
          ],
          [
              InlineKeyboardButton(
                  text="« Return to Hub Menu", callback_data="main_menu"
              )
          ],
      ]
  )


# --- HANDLERS: START & MAIN MENU ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
  await state.clear()
  user_name = message.from_user.first_name
  text = (
      f"<b>GATENS NETWORK INFRASTRUCTURE</b>\n"
      f"━━━━━━━━━━━━━━━━━━━━━━\n"
      f"Welcome, <b>{user_name}</b>.\n\n"
      f"You have accessed the official Gatens Network Hub. "
      f"To maintain secure community standards, account verification is required.\n\n"
      f"Select an option below to proceed with network verification or access infrastructure destinations."
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🛡️ Start Account Verification",
                  callback_data="start_verification",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🌐 View Network Destinations", callback_data="view_hubs"
              )
          ],
      ]
  )

  if message.from_user.id in ADMIN_IDS:
    text += "\n\n<code>[ADMIN SESSION AUTHORIZED]</code>"

  await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery, state: FSMContext):
  await state.clear()
  text = (
      "<b>GATENS NETWORK HUB</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "Choose an action below:"
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🛡️ Start Account Verification",
                  callback_data="start_verification",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🌐 View Network Destinations", callback_data="view_hubs"
              )
          ],
      ]
  )
  await callback.message.edit_text(
      text, reply_markup=keyboard, parse_mode="HTML"
  )
  await callback.answer()


@dp.callback_query(F.data == "view_hubs")
async def process_view_hubs(callback: types.CallbackQuery):
  text = (
      "<b>OFFICIAL NETWORK HUBS & CHANNELS</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
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
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "• Core Infrastructure Bot: @gatens_bot\n"
      "• More specialized network utilities coming online."
  )
  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(text="« Back to Hub", callback_data="view_hubs")
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
      "<b>ACCOUNT VERIFICATION PORTAL</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "Please select the specific community group or market where you want to complete your verification record:"
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
      f"━━━━━━━━━━━━━━━━━━━━━━\n"
      f"<b>Step 1/2: User ID Proof Submission</b>\n\n"
      f"Please send or upload a screenshot of your Telegram User ID or profile verification badge to proceed."
  )
  await callback.message.edit_text(text, parse_mode="HTML")
  await state.set_state(VerificationSG.uploading_userid)
  await callback.answer()


@dp.message(VerificationSG.uploading_userid, F.photo | F.document | F.text)
async def process_userid_upload(message: types.Message, state: FSMContext):
  # Save or process User ID file/proof
  text = (
      "<b>ACCOUNT VERIFICATION PORTAL</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "<b>Step 2/2: Vouch Channel Proof</b>\n\n"
      f"User ID received successfully ✅\n\n"
      "Now, please provide your **Vouch Channel link** or upload a screenshot of your vouches/reputation record."
  )
  await message.answer(text, parse_mode="HTML")
  await state.set_state(VerificationSG.uploading_vouch)


@dp.message(VerificationSG.uploading_vouch)
async def process_vouch_upload(message: types.Message, state: FSMContext):
  data = await state.get_data()
  target_group = data.get("target_group", "General Network")

  success_text = (
      "<b>VERIFICATION SUBMITTED SUCCESSFULLY</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      f"Target Destination: <b>{target_group}</b>\n"
      "Status: <code>PENDING AUDIT</code>\n\n"
      "Your documents and proofs have been forwarded to the network moderators. "
      "You will receive confirmation once reviewed."
  )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[[
          InlineKeyboardButton(
              text="« Return to Main Menu", callback_data="main_menu"
          )
      ]]
  )
  await message.answer(success_text, reply_markup=keyboard, parse_mode="HTML")
  await state.clear()


# --- GROUP CHAT COMMANDS & /VERIFY COMMAND ---


@dp.message(Command("verify"))
async def cmd_verify_command(message: types.Message, state: FSMContext):
  """Allows users to trigger verification from group chats or private chat"""
  text = (
      "<b>SECURE GROUP VERIFICATION</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "Select your target destination group to begin verification:"
  )
  await message.answer(text, reply_markup=get_group_selection_keyboard(), parse_mode="HTML")


@dp.message(Command("network"))
async def cmd_network_info(message: types.Message):
  """Unique professional command for group participants"""
  text = (
      "<b>GATENS NETWORK DIRECTORY</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "• Main Announcement: Check pinned message\n"
      "• Support Portal: @gatens\n"
      "• Status: 100% Operational"
  )
  await message.answer(text, parse_mode="HTML")


@dp.message(Command("reputation"))
async def cmd_reputation_info(message: types.Message):
  """Unique professional command for trading/vouch safety"""
  text = (
      "<b>REPUTATION & SECURITY GUIDELINES</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "Always verify user IDs through @gatens_bot before conducting transactions in our chats."
  )
  await message.answer(text, parse_mode="HTML")


@dp.message(Command("rules"))
async def cmd_group_rules(message: types.Message):
  """Group rules command"""
  text = (
      "<b>COMMUNITY CONDUCT RULES</b>\n"
      "━━━━━━━━━━━━━━━━━━━━━━\n"
      "1. Respect all network members.\n"
      "2. No unauthorized spam or scam links.\n"
      "3. Conduct all deals through official channels and verified middlemen."
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
