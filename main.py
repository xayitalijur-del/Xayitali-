import asyncio
import logging
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, 
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError

BOT_TOKEN = "8999006159:AAGrXALukv0f-gucJR4i6xEhv-RnoHmgSO4"
GEMINI_API_KEY = "AQ.Ab8RN6KLEEDqjXUKTZHEz6uDkoQMZFGLHPQWa0qxM91WMvfalg"
ADMIN_ID = 1927054009
TELEGRAM_LINK = "https://t.me/tez_meb"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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

TEXTS = {
    "uz": {
        "welcome": "Assalomu alaykum! *'Tez Mebel'* rasmiy botiga xush kelibsiz! 🛠️ ✨\n\nSavolingiz bo'lsa bemalol yozing yoki menyudan foydalaning!",
        "btn_order": "📝 Buyurtma berish / O'lcham olish",
        "btn_about": "ℹ️ Biz haqimizda",
        "btn_contact": "📞 Aloqa",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
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
        "lang_changed": "Til muvaffaqiyatli o'zgartirildi! 🇺🇿"
    },
    "ru": {
        "welcome": "Здравствуйте! Добро пожаловать в официальный бот *'Tez Mebel'*! 🛠️ ✨\n\nЗадавайте вопросы или используйте меню ниже!",
        "btn_order": "📝 Заказать / Вызов замерщика",
        "btn_about": "ℹ️ О нас",
        "btn_contact": "📞 Контакты",
        "btn_change_lang": "🌐 Сменить язык",
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
        "lang_changed": "Язык успешно изменен! 🇷🇺"
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

def get_name_keyboard(telegram_name: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=telegram_name)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_phone_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXTS[lang]["btn_phone"], request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_location_keyboard(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=TEXTS[lang]["btn_location"], request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_furniture_keyboard(lang: str):
    f = TEXTS[lang]["furnitures"]
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f[0]), KeyboardButton(text=f[1])],
            [KeyboardButton(text=f[2]), KeyboardButton(text=f[3])],
            [KeyboardButton(text=f[4])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

async def get_gemini_response(user_text: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\nMijoz xabari: {user_text}"}]}]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=10) as response:
            if response.status == 200:
                data = await response.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            raise Exception(f"API Error Code: {response.status}")

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Iltimos, tilni tanlang / Пожалуйста, выберите язык:",
        reply_markup=get_lang_keyboard()
    )
    await state.set_state(OrderState.waiting_for_lang)

@dp.message(Command("lang"))
@dp.message(F.text.in_(["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]))
async def change_lang_handler(message: Message, state: FSMContext):
    await message.answer(
        "Iltimos, yangi tilni tanlang / Пожалуйста, выберите новый язык:",
        reply_markup=get_lang_keyboard()
    )
    await state.set_state(OrderState.waiting_for_lang)

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
    data = await state.get_data()
    lang = data.get("lang", "uz")
    telegram_name = message.from_user.first_name or "Mijoz"
    
    await message.answer(
        TEXTS[lang]["ask_name"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_name_keyboard(telegram_name)
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
            await bot.send_message(chat_id=ADMIN_ID, text=f"📍 *Manzil:* {location}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Adminga yuborishda xatolik: {e}")

    await state.set_state(None)

@dp.message(F.text.in_(["ℹ️ Biz haqimizda", "ℹ️ О нас"]))
async def about_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await message.answer(TEXTS[lang]["about_text"], parse_mode=ParseMode.MARKDOWN)

@dp.message(F.text.in_(["📞 Aloqa", "📞 Контакты"]))
async def contact_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "uz")
    contact_btn = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=TEXTS[lang]["btn_tg_link"], url=TELEGRAM_LINK)]]
    )
    await message.answer(TEXTS[lang]["contact_text"], parse_mode=ParseMode.MARKDOWN, reply_markup=contact_btn)

@dp.message(F.text)
async def ai_chat_handler(message: Message):
    if message.from_user.is_bot:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    user = message.from_user
    name = user.full_name
    username = f"@{user.username}" if user.username else "Kiritilmagan"
    user_id = user.id
    user_text = message.text

    try:
        ai_reply = await get_gemini_response(user_text)
        await message.answer(ai_reply)

        # Mijozning xabari va AI bergan javobni adminga yuborish
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

async def main():
    print("Tezkor Premium AI Boti ishga tushdi...")
    while True:
        try:
            await dp.start_polling(bot)
        except (TelegramNetworkError, Exception):
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(main())
