import asyncio
import logging
import os
import aiohttp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    BufferedInputFile
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError

BOT_TOKEN = "8708329718:AAETLtIatPvg6DvfrP5Zf9EtqMLu4Czf3RA"
GEMINI_API_KEY = "AQ.Ab8RN6JSIoDZP1aqzV0-XNoDbuviWI5fuXVQryMoZ9S0P04tFw"
ADMIN_ID = 1927054009
TELEGRAM_LINK = "https://t.me/tez_meb"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Oddiy xotirada mijozlar va yozishmalarni saqlash uchun bazalar
all_users = set()
chat_history_logs = []

SYSTEM_PROMPT = (
    "Siz 'Tez Mebel' premium mebel kompaniyasining professional va xushmuomala AI-konsultantisiz. "
    "Mijozlarga mebel turlari (oshxona, yotoqxona, mebel jihozlari), materiallar (MDF, LDSP, Akril) "
    "va sifat bo'yicha aniq, qisqa va tushunarli maslahatlar bering. "
    "Mijoz qaysi tilda (o'zbek yoki rus tilida) yozsa, xuddi shu tilda javob bering. "
    "Agar mijoz buyurtma bermoqchi bo'lsa yoki aniq hisob-kitob so'rasa, "
    "unga '📝 Buyurtma berish / Заказать' tugmasini bosishni taklif qiling."
)

class OrderState(StatesGroup):
    waiting_for_lang = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_location = State()
    waiting_for_furniture = State()
    waiting_for_broadcast = State() # Admin xat yuborishi uchun

TEXTS = {
    "uz": {
        "welcome": "Assalomu alaykum! *'Tez Mebel'* rasmiy botiga xush kelibsiz! 🛠️ ✨\n\nSavolingiz bo'lsa bemalol yozing yoki menyudan foydalaning!",
        "btn_order": "📝 Buyurtma berish / O'lcham olish",
        "btn_about": "ℹ️ Biz haqimizda",
        "btn_contact": "📞 Aloqa",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
        "btn_home": "🏠 Bosh sahifa",
        "ask_name": "Buyurtma rasmiylashtirish uchun, iltimos, *ismingizni* kiriting yoki quyidagi tugmani bosing:",
        "ask_phone": "Rahmat, {name}! Endi *telefon raqamingizni* yuboring:",
        "btn_phone": "📱 Telefon raqamni yuborish",
        "ask_location": "Ajoyib! Endi yetkazib berish yoki o'lcham olish uchun *lokatsiyangizni* yuboring:",
        "btn_location": "📍 Lokatsiyani yuborish",
        "ask_furniture": "Qanday mebel kerakligini tugmalardan tanlang yoki o'z variantingizni yozib yuboring:",
        "furnitures": ["Oshxona", "Shkaf", "Doʻkon", "Apteka", "Aksessuar"],
        "order_done": "Rahmat! Buyurtmangiz qabul qilindi. Tez orada usta siz bilan bog'lanadi. 🛠️",
        "about_text": "✨ *Tez Mebel* — har qanday turdagi mebellarni sifatli va hamyonbop narxlarda tayyorlab berish xizmati.\n\n🔹 Tajribali ustalar\n🔹 Zamonaviy dizayn va sifatli materiallar\n🔹 Tezkor o'lcham olish va yetkazib berish",
        "contact_text": "📞 *Biz bilan bog'lanish:*\n\nSavollaringiz va takliflaringiz bo'lsa, mutaxassisimizga bemalol murojaat qilishingiz mumkin.",
        "btn_tg_link": "💬 Telegram orqali bog'lanish",
        "lang_changed": "Til muvaffaqiyatli o'zgartirildi! 🇺🇿",
        "home_text": "Siz asosiy menyuga qaytdingiz. Kerakli bo'limni tanlang:"
    },
    "ru": {
        "welcome": "Здравствуйте! Добро пожаловать в официальный бот *'Tez Mebel'*! 🛠️ ✨\n\nЗадавайте вопросы или используйте меню ниже!",
        "btn_order": "📝 Заказать / Вызов замерщика",
        "btn_about": "ℹ️ О нас",
        "btn_contact": "📞 Контакты",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_home": "🏠 Главная страница",
        "ask_name": "Для оформления заказа, пожалуйста, введите ваше *имя* или нажмите кнопку ниже:",
        "ask_phone": "Спасибо, {name}! Теперь отправьте ваш *номер телефона*:",
        "btn_phone": "📱 Отправить номер телефона",
        "ask_location": "Отлично! Теперь отправьте вашу *локацию* для доставки или замера:",
        "btn_location": "📍 Отправить локацию",
        "ask_furniture": "Выберите нужную мебель из кнопок или напишите свой вариант:",
        "furnitures": ["Кухня", "Шкаф", "Магазин", "Аптека", "Аксессуары"],
        "order_done": "Спасибо! Ваш заказ принят. Мастер свяжется с вами в ближайшее время. 🛠️",
        "about_text": "✨ *Tez Mebel* — изготовление качественной мебели по доступным ценам.\n\n🔹 Опытные мастера\n🔹 Современный дизайн и качественные материалы\n🔹 Быстрый замер и доставка",
        "contact_text": "📞 *Связаться с нами:*\n\nПо всем вопросам и предложениям обращайтесь к нашему специалисту.",
        "btn_tg_link": "💬 Связаться через Telegram",
        "lang_changed": "Язык успешно изменен! 🇷🇺",
        "home_text": "Вы вернулись в главное меню. Выберите нужный раздел:"
    }
}

def get_lang_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🇺🇿 O'zbekcha"), KeyboardButton(text="🇷🇺 Русский")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_main_keyboard(lang: str):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["btn_order"])],
            [KeyboardButton(text=t["btn_about"]), KeyboardButton(text=t["btn_contact"])],
            [KeyboardButton(text=t["btn_change_lang"])]
        ],
        resize_keyboard=True
    )

def get_name_keyboard(telegram_name: str, lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=telegram_name)],
            [KeyboardButton(text=TEXTS[lang]["btn_home"])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_phone_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["btn_phone"], request_contact=True)],
            [KeyboardButton(text=TEXTS[lang]["btn_home"])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_location_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS[lang]["btn_location"], request_location=True)],
            [KeyboardButton(text=TEXTS[lang]["btn_home"])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_furniture_keyboard(lang: str):
    f = TEXTS[lang]["furnitures"]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f[0]), KeyboardButton(text=f[1])],
            [KeyboardButton(text=f[2]), KeyboardButton(text=f[3])],
            [KeyboardButton(text=f[4])],
            [KeyboardButton(text=TEXTS[lang]["btn_home"])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Admin panel uchun inline tugmalar
def get_admin_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📁 Yozishmalarni yuklab olish (.txt)", callback_data="admin_download")],
            [InlineKeyboardButton(text="📢 Hammaga xabar yuborish", callback_data="admin_broadcast")]
        ]
    )

async def get_gemini_response(user_text: str) -> str:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nMijoz xabari: {user_text}"}]}]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=15) as response:
            if response.status == 200:
                data = await response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                error_text = await response.text()
                logging.error(f"Gemini API xatosi ({response.status}): {error_text}")
                raise Exception(f"API Error Code: {response.status}")

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    await state.clear()
    await message.answer(
        "Iltimos, tilni tanlang / Пожалуйста, выберите язык:",
        reply_markup=get_lang_keyboard()
    )
    await state.set_state(OrderState.waiting_for_lang)

@dp.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await message.answer(
        "🛠 *Admin boshqaruv paneli*ga xush kelibsiz!\nKerakli amalni tanlang:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

# Admin tugmalari (Callback)
@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(callback: types.CallbackQuery if 'types' in globals() else callback_query_handler_placeholder, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Siz admin emassiz!", show_alert=True)
        return

    action = callback.data
    if action == "admin_stats":
        total_users = len(all_users)
        total_chats = len(chat_history_logs)
        stats_text = (
            f"📊 *Bot statistikasi:*\n\n"
            f"👥 Jami foydalanuvchilar: {total_users} ta\n"
            f"💬 Jami yozishmalar: {total_chats} ta"
        )
        await callback.message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)
        await callback.answer()

    elif action == "admin_download":
        if not chat_history_logs:
            await callback.answer("Hozircha yozishmalar mavjud emas!", show_alert=True)
            return
        
        file_content = "\n".join(chat_history_logs)
        file_bytes = file_content.encode("utf-8")
        document = BufferedInputFile(file_bytes, filename="mijozlar_yozishmalari.txt")
        
        await callback.message.answer_document(document=document, caption="📁 Barcha mijozlar yozishmalari tarixi.")
        await callback.answer()

    elif action == "admin_broadcast":
        await callback.message.answer("📢 Barcha mijozlarga yubormoqchi bo'lgan xabaringizni kiriting:")
        await state.set_state(OrderState.waiting_for_broadcast)
        await callback.answer()

@dp.message(OrderState.waiting_for_broadcast, F.text)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    broadcast_text = message.text
    await state.clear()
    
    success_count = 0
    fail_count = 0
    
    status_msg = await message.answer("⏳ Xabarlar tarqatilmoqda...")

    for user_id in all_users:
        try:
            await bot.send_message(chat_id=user_id, text=f"📢 *E'lon:*\n\n{broadcast_text}", parse_mode=ParseMode.MARKDOWN)
            success_count += 1
            await asyncio.sleep(0.05) # Telegram limitiga tushmaslik uchun
        except Exception:
            fail_count += 1

    await status_msg.edit_text(
        f"✅ Xabar tarqatish yakunlandi!\n\n"
        f"Muvaffaqiyatli yuborildi: {success_count} ta\n"
        f"Xatolik (bloklaganlar): {fail_count} ta"
    )

@dp.message(Command("lang"))
@dp.message(F.text.in_(["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]))
async def change_lang_handler(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    await message.answer(
        "Iltimos, yangi tilni tanlang / Пожалуйста, выберите новый язык:",
        reply_markup=get_lang_keyboard()
    )
    await state.set_state(OrderState.waiting_for_lang)

@dp.message(F.text.in_(["🏠 Bosh sahifa", "🏠 Главная страница"]))
async def go_home(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await state.clear()
    await state.update_data(lang=lang)
    await message.answer(
        TEXTS[lang]["home_text"],
        reply_markup=get_main_keyboard(lang)
    )

@dp.message(OrderState.waiting_for_lang, F.text.in_(["🇺🇿 O'zbekcha", "🇷🇺 Русский"]))
async def set_language(message: Message, state: FSMContext):
    lang = "uz" if message.text == "🇺🇿 O'zbekcha" else "ru"
    await state.update_data(lang=lang)
    
    await message.answer(
        TEXTS[lang]["lang_changed"] + "\n\n" + TEXTS[lang]["welcome"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(lang)
    )
    await state.set_state(None)

@dp.message(F.text.in_(["📝 Buyurtma berish / O'lcham olish", "📝 Заказать / Вызов замерщика"]))
async def start_order(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    telegram_name = message.from_user.first_name or "Mijoz"
    
    await message.answer(
        TEXTS[lang]["ask_name"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_name_keyboard(telegram_name, lang)
    )
    await state.set_state(OrderState.waiting_for_name)

@dp.message(OrderState.waiting_for_name, F.text)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    data = await state.get_data()
    lang = data.get("lang", "uz")

    await message.answer(
        TEXTS[lang]["ask_phone"].format(name=message.text),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_phone_keyboard(lang)
    )
    await state.set_state(OrderState.waiting_for_phone)

@dp.message(OrderState.waiting_for_phone, F.contact | F.text)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    await state.update_data(phone=phone)
    data = await state.get_data()
    lang = data.get("lang", "uz")

    await message.answer(
        TEXTS[lang]["ask_location"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_location_keyboard(lang)
    )
    await state.set_state(OrderState.waiting_for_location)

@dp.message(OrderState.waiting_for_location, F.location | F.text)
async def process_location(message: Message, state: FSMContext):
    loc_data = {"latitude": message.location.latitude, "longitude": message.location.longitude} if message.location else message.text
    await state.update_data(location=loc_data)
    data = await state.get_data()
    lang = data.get("lang", "uz")

    await message.answer(
        TEXTS[lang]["ask_furniture"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_furniture_keyboard(lang)
    )
    await state.set_state(OrderState.waiting_for_furniture)

@dp.message(OrderState.waiting_for_furniture, F.text)
async def process_furniture(message: Message, state: FSMContext):
    furniture_detail = message.text
    user_data = await state.get_data()
    lang = user_data.get("lang", "uz")
    
    name = user_data.get("name")
    phone = user_data.get("phone")
    location = user_data.get("location")
    user_id = message.from_user.id
    username = message.from_user.username

    await message.answer(
        TEXTS[lang]["order_done"],
        reply_markup=get_main_keyboard(lang)
    )

    admin_text = (
        "📥 *Yangi buyurtma kelib tushdi!*\n\n"
        f"🌐 *Til:* {lang.upper()}\n"
        f"👤 *Ismi:* {name}\n"
        f"📞 *Telefon:* `{phone}`\n"
        f"🛋 *Mebel turi:* {furniture_detail}\n"
    )

    user_link = f"https://t.me/{username}" if username else f"tg://user?id={user_id}"
    user_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Mijoz bilan bog'lanish", url=user_link)]]
    )

    try:
        await bot.send_message(
            chat_id=ADMIN_ID, 
            text=admin_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=user_keyboard
        )
        if isinstance(location, dict):
            await bot.send_location(chat_id=ADMIN_ID, latitude=location["latitude"], longitude=location["longitude"])
        else:
            await bot.send_message(chat_id=ADMIN_ID, text=f"📍 *Manzil:* {location}", parse_Mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Adminga yuborishda xatolik: {e}")

    await state.set_state(None)

@dp.message(F.text.in_(["ℹ️ Biz haqimizda", "ℹ️ О нас"]))
async def about_handler(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await message.answer(
        TEXTS[lang]["about_text"], 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(lang)
    )

@dp.message(F.text.in_(["📞 Aloqa", "📞 Контакты"]))
async def contact_handler(message: Message, state: FSMContext):
    all_users.add(message.from_user.id)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await message.answer(
        TEXTS[lang]["contact_text"], 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=get_main_keyboard(lang)
    )

@dp.message(F.text)
async def ai_chat_handler(message: Message):
    if message.from_user.is_bot:
        return

    all_users.add(message.from_user.id)
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    user = message.from_user
    name = user.full_name
    username = f"@{user.username}" if user.username else "Kiritilmagan"
    user_id = user.id
    user_text = message.text

    try:
        ai_reply = await get_gemini_response(user_text)
        await message.answer(ai_reply)

        # Loglarni .txt uchun yig'ib boramiz
        log_entry = f"Mijoz: {name} ({username}) [ID: {user_id}]\nSavol: {user_text}\nAI Javob: {ai_reply}\n" + "-"*40
        chat_history_logs.append(log_entry)

        user_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user_id}"
        admin_report = (
            f"💬 *Mijoz va AI yozishmasi:*\n\n"
            f"👤 *Mijoz:* {name} ({username})\n"
            f"🆔 *ID:* `{user_id}`\n\n"
            f"❓ *Mijozning savoli:* \n{user_text}\n\n"
            f"🤖 *AI bergan javob:* \n{ai_reply}"
        )
        admin_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="💬 Mijozga yozish", url=user_link)]]
        )
        await bot.send_message(chat_id=ADMIN_ID, text=admin_report, parse_mode=ParseMode.MARKDOWN, reply_markup=admin_keyboard)

    except Exception as e:
        logging.error(f"Gemini API xatosi: {e}")
        await message.answer("Xabaringiz qabul qilindi. Tez orada mutaxassisimiz javob beradi!")

async def handle_web(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    print("Tezkor Premium AI Boti va Admin Panel ishga tushdi...")
    await bot.delete_webhook(drop_pending_updates=True)
    await start_web_server()
    
    while True:
        try:
            await dp.start_polling(bot, drop_pending_updates=True)
        except (TelegramNetworkError, Exception) as e:
            logging.error(f"Polling xatosi: {e}")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
