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


if name == "main":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped")
