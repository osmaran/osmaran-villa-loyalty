import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = "https://osmaran-villa-loyalty.vercel.app"
SUPABASE_URL = "https://ahsepjswkdhmjtsoogqt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFoc2VwanN3a2RobWp0c29vZ3F0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTQ4OTEwNDQsImV4cCI6MjExMDQ2NzA0NH0.ZgND289FS56etizFmpmUXan8KGl9R7o7kHOBX4cY9OM"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

pending_referrals = {}

def get_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Открыть кабинет Osmaran Villa", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])

def get_contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом / Raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandObject):
    tg_id = message.from_user.id
    args = command.args
    if args and args.startswith("ref_"):
        try:
            ref_id = int(args.replace("ref_", ""))
            if ref_id != tg_id:
                pending_referrals[tg_id] = ref_id
        except ValueError:
            pass

    res = db.table("users").select("*").eq("telegram_id", tg_id).execute()
    user = res.data[0] if res.data else None

    if user and user.get("phone"):
        await message.answer(
            f"Добро пожаловать в **Osmaran Villa**, {user.get('full_name')}!\n\n"
            f"💰 Ваш текущий баланс: **{user.get('balance'):,} сум**\n"
            f"Нажмите кнопку ниже, чтобы открыть личный кабинет, заказать VIP-услуги или пригласить друзей:",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            "Добро пожаловать в программу лояльности **Osmaran Villa**! 🏡\n\n"
            "Для регистрации и получения приветственного бонуса **100 000 сум** на баланс, пожалуйста, нажмите кнопку ниже, чтобы поделиться номером телефона:",
            reply_markup=get_contact_keyboard(),
            parse_mode="Markdown"
        )

@dp.message(F.contact)
async def handle_contact(message: types.Message):
    contact = message.contact
    tg_id = message.from_user.id
    full_name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or message.from_user.full_name
    phone = contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone

    settings_res = db.table("settings").select("welcome_bonus").eq("id", 1).execute()
    welcome_bonus = settings_res.data[0]["welcome_bonus"] if settings_res.data else 100000

    res = db.table("users").select("*").eq("telegram_id", tg_id).execute()
    existing_user = res.data[0] if res.data else None
    referred_by = pending_referrals.get(tg_id)

    if existing_user:
        db.table("users").update({
            "full_name": full_name,
            "phone": phone
        }).eq("telegram_id", tg_id).execute()
    else:
        user_data = {
            "telegram_id": tg_id,
            "full_name": full_name,
            "phone": phone,
            "balance": welcome_bonus,
            "referral_code": f"ref_{tg_id}"
        }
        if referred_by:
            user_data["referred_by"] = referred_by
        db.table("users").insert(user_data).execute()

        db.table("transactions").insert({
            "user_telegram_id": tg_id,
            "amount": welcome_bonus,
            "tx_type": "welcome",
            "comment": "Приветственный Welcome-бонус за регистрацию"
        }).execute()

    await message.answer(
        f"✅ Регистрация завершена, **{full_name}**!\n\n"
        f"🎁 Вам начислен приветственный бонус: **{welcome_bonus:,} сум**.\n"
        f"Вы можете оплатить ими до 100% VIP-услуг или использовать как скидку до 30% на аренду виллы.",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await message.answer(
        "Откройте ваш личный кабинет **Osmaran Villa**:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def health_check(request):
    return web.Response(text="Osmaran Villa Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
