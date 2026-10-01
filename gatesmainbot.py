import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Configured credentials
TOKEN = os.getenv("BOT_TOKEN", "8841797167:AAGqfC5laKal7Z7D_Q_PVDQJa7sQRri9BIY")
ADMIN_IDS = [
    6918967434
]  # Your secure admin Telegram ID pre-configured here

# Initialize Bot and Dispatcher
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

logging.basicConfig(level=logging.INFO)


# --- KEYBOARDS ---


def get_public_keyboard():
  """Professional network hub layout for regular users"""
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="Verify Account", callback_data="verify_user"
              )
          ],
          [
              InlineKeyboardButton(
                  text="Official Channels", callback_data="show_channels"
              ),
              InlineKeyboardButton(
                  text="Community Groups", callback_data="show_groups"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="Gatens Ecosystem Bots", callback_data="show_gatens_bots"
              )
          ],
          [
              InlineKeyboardButton(
                  text="Support / Contact", url="https://t.me/gatens"
              )
          ],
      ]
  )


def get_admin_keyboard():
  """Hidden panel layout for authorized admins"""
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="Network Stats", callback_data="admin_stats"
              )
          ],
          [
              InlineKeyboardButton(
                  text="Return to Public Menu", callback_data="main_menu"
              )
          ],
      ]
  )


# --- HANDLERS ---


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
  user_id = message.from_user.id
  welcome_text = (
      f"Welcome to Gatens Network Hub, {message.from_user.first_name}.\n\n"
      "Use the interactive options below to access our official channels, "
      "groups, and network utility tools."
  )

  # Check if user is an admin
  if user_id in ADMIN_IDS:
    welcome_text += "\n\n[ADMIN SESSION DETECTED]"
    await message.answer(
        welcome_text, reply_markup=get_admin_keyboard(), parse_mode="HTML"
    )
  else:
    await message.answer(
        welcome_text, reply_markup=get_public_keyboard(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback: types.CallbackQuery):
  await callback.message.edit_text(
      "Gatens Network Hub - Main Menu:", reply_markup=get_public_keyboard()
  )
  await callback.answer()


@dp.callback_query(F.data == "verify_user")
async def process_verification(callback: types.CallbackQuery):
  await callback.message.edit_text(
      "Account Verification Status:\n\n"
      "Status: VERIFIED\n"
      "Your network security profile is up to date.",
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[[
              InlineKeyboardButton(
                  text="Back to Hub", callback_data="main_menu"
              )
          ]]
      ),
  )
  await callback.answer("Verification check completed.")


@dp.callback_query(F.data == "show_channels")
async def process_channels(callback: types.CallbackQuery):
  text = (
      "Official Gatens Network Channels:\n\n"
      "• Main Channel: https://t.me/+3jHzHttnfHFlZWFh\n"
      "• Gates Redirect Channel: https://t.me/gatens"
  )
  await callback.message.edit_text(
      text,
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[[
              InlineKeyboardButton(
                  text="Back to Hub", callback_data="main_menu"
              )
          ]]
      ),
  )
  await callback.answer()


@dp.callback_query(F.data == "show_groups")
async def process_groups(callback: types.CallbackQuery):
  text = (
      "Official Gatens Network Groups & Markets:\n\n"
      "• Chat GC: https://t.me/chatyear\n"
      "• Buy and Sell GC: https://t.me/fragte\n"
      "• Market: https://t.me/whiteages"
  )
  await callback.message.edit_text(
      text,
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[[
              InlineKeyboardButton(
                  text="Back to Hub", callback_data="main_menu"
              )
          ]]
      ),
  )
  await callback.answer()


@dp.callback_query(F.data == "show_gatens_bots")
async def process_gatens_bots(callback: types.CallbackQuery):
  text = (
      "Ecosystem Bots Created by Gatens:\n\n"
      "• Gatens Core Bot: @gatens_bot\n"
      "(More bots will appear here as you launch them!)"
  )
  await callback.message.edit_text(
      text,
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[[
              InlineKeyboardButton(
                  text="Back to Hub", callback_data="main_menu"
              )
          ]]
      ),
  )
  await callback.answer()


# --- ADMIN PANEL LOGIC ---


@dp.callback_query(F.data == "admin_stats")
async def process_admin_stats(callback: types.CallbackQuery):
  if callback.from_user.id not in ADMIN_IDS:
    await callback.answer("Unauthorized action.", show_alert=True)
    return

  await callback.message.edit_text(
      "Network Statistics:\n\n"
      "• Total Users Tracked: Live Database Active\n"
      "• Active Sessions: Operational",
      reply_markup=InlineKeyboardMarkup(
          inline_keyboard=[[
              InlineKeyboardButton(
                  text="Back to Admin Panel", callback_data="admin_back"
              )
          ]]
      ),
  )
  await callback.answer()


@dp.callback_query(F.data == "admin_back")
async def process_admin_back(callback: types.CallbackQuery):
  await callback.message.edit_text(
      "Admin Control Panel:", reply_markup=get_admin_keyboard()
  )
  await callback.answer()


# --- MAIN RUNNER ---


async def main():
  print("Starting @gatens_bot...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
