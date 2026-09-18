import asyncio
import logging
import os
import asyncpg
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
    BufferedInputFile,
    CallbackQuery
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError

BOT_TOKEN = "8708329718:AAETLtIatPvg6DvfrP5Zf9EtqMLu4Czf3RA"
GEMINI_API_KEY = "AQ.Ab8RN6JSIoDZP1aqzV0-XNoDbuviWI5fuXVQryMoZ9S0P04tFw"
ADMIN_ID = 1927054009

# Supabase PostgreSQL ulanish manzili
DATABASE_URL = "postgresql://postgres:Saroy2645142x@db.uktemyykoirfrweqjhsm.supabase.co:5432/postgres"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

CATEGORIES = ["Oshxona", "Shkaf", "Doʻkon", "Apteka", "Aksessuar"]

# --- POSTGRESQL BAZA BILAN ISHLASH (Supabase) ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                user_name TEXT,
                question TEXT,
                ai_answer TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                name TEXT,
                phone TEXT,
                location TEXT,
                furniture TEXT,
                photo_id TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS catalog (
                id SERIAL PRIMARY KEY,
                category TEXT,
                photo_id TEXT,
                title TEXT,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    finally:
        await conn.close()

async def db_add_user(user_id, full_name, username):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO users (user_id, full_name, username) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO NOTHING",
            user_id, full_name, username
        )
    finally:
        await conn.close()

async def db_log_chat(user_id, user_name, question, ai_answer):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO chats (user_id, user_name, question, ai_answer) VALUES ($1, $2, $3, $4)",
            user_id, user_name, question, ai_answer
        )
    finally:
        await conn.close()

async def db_save_order(user_id, name, phone, location, furniture, photo_id):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO orders (user_id, name, phone, location, furniture, photo_id) VALUES ($1, $2, $3, $4, $5, $6)",
            user_id, name, phone, str(location), furniture, photo_id
        )
    finally:
        await conn.close()

async def db_add_catalog_item(category, photo_id, title, description):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO catalog (category, photo_id, title, description) VALUES ($1, $2, $3, $4)",
            category, photo_id, title, description
        )
    finally:
        await conn.close()

async def db_get_catalog_items_by_category(category):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetch(
            "SELECT id, photo_id, title, description FROM catalog WHERE category = $1 ORDER BY id DESC", category
        )
    finally:
        await conn.close()

async def db_get_catalog_item_by_id(item_id):
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetchrow(
            "SELECT id, photo_id, title, description FROM catalog WHERE id = $1", item_id
        )
    finally:
        await conn.close()

async def db_get_stats():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        u_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        c_count = await conn.fetchval("SELECT COUNT(*) FROM chats")
        o_count = await conn.fetchval("SELECT COUNT(*) FROM orders")
        return u_count, c_count, o_count
    finally:
        await conn.close()

async def db_get_all_users():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [row["user_id"] for row in rows]
    finally:
        await conn.close()

async def db_get_chat_logs():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetch("SELECT user_name, question, ai_answer, timestamp FROM chats ORDER BY id DESC")
    finally:
        await conn.close()

async def db_get_orders():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        return await conn.fetch("SELECT name, phone, location, furniture, timestamp FROM orders ORDER BY id DESC")
    finally:
        await conn.close()

# --- AI TIZIMI ---
SYSTEM_PROMPT = (
    "Siz 'Tez Mebel' premium mebel kompaniyasining professional, ziyrak va xushmuomala AI-konsultantisiz. "
    "Mijozlarga oshxona, yotoqxona, shkaf, do'kon va apteka jihozlari, materiallar (MDF, LDSP, Akril) "
    "bo'yicha eng aniq va sifatli maslahatlar bering. "
    "Mijoz qaysi tilda (o'zbek yoki rus tilida) yozsa, xuddi shu tilda mukammal javob bering. "
    "Agar mijoz narx yoki buyurtma haqida so'rasa, unga zudlik bilan '📝 Buyurtma berish / Заказать' tugmasini bosishni tavsiya qiling."
)

class OrderState(StatesGroup):
    waiting_for_lang = State()
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_location = State()
    waiting_for_furniture = State()
    waiting_for_broadcast = State()
    waiting_for_cat_category = State()
    waiting_for_cat_photo = State()
    waiting_for_cat_title = State()
    waiting_for_cat_desc = State()

TEXTS = {
    "uz": {
        "welcome": "Assalomu alaykum! *'Tez Mebel'* rasmiy premium botiga xush kelibsiz! 🛠️ ✨\n\nSavollaringizni yuboring yoki quyidagi menyudan foydalaning:",
        "btn_order": "📝 Buyurtma berish / O'lcham olish",
        "btn_catalog": "🗂 Mebellar katalogi",
        "btn_about": "ℹ️ Biz haqimizda",
        "btn_contact": "📞 Aloqa",
        "btn_change_lang": "🌐 Tilni o'zgartirish",
        "btn_home": "🏠 Bosh sahifa",
        "ask_name": "Buyurtmani rasmiylashtirish uchun, iltimos, *ismingizni* kiriting yoki pastdagi tugmani bosing:",
        "ask_phone": "Rahmat, {name}! Endi *telefon raqamingizni* yuboring:",
        "btn_phone": "📱 Telefon raqamni yuborish",
        "ask_location": "Ajoyib! Endi usta kelishi uchun *lokatsiyangizni* yuboring:",
        "btn_location": "📍 Lokatsiyani yuborish",
        "ask_furniture": "Qanday turdagi mebel buyurtma qilmoqchisiz? Tanlang yoki yozib yuboring:",
        "order_done": "Rahmat! Buyurtmangiz qabul qilindi. Tez orada mutaxassisimiz siz bilan bog'lanadi. 🛠️",
        "about_text": "✨ *Tez Mebel* — har qanday turdagi dizayn asosida sifatli va ishonchli mebellarni tayyorlab berish xizmati.\n\n🔹 Premium materiallar (MDF, Akril, LDSP)\n🔹 Tajribali ustalar va tezkor o'lcham olish\n🔹 Kafolatli sifat va hamyonbop narxlar",
        "contact_text": "📞 *Biz bilan bog'lanish:*\n\n📞 Tel: +998 (90) 123-45-67\n📍 Manzil: Toshkent shahri\n⏱ Ish vaqti: 09:00 - 19:00",
        "lang_changed": "Til muvaffaqiyatli o'zgartirildi! 🇺🇿",
        "home_text": "Siz asosiy menyuga qaytdingiz. Kerakli bo'limni tanlang:",
        "catalog_choose": "🗂 Kerakli mebel kategoriyasini tanlang:"
    },
    "ru": {
        "welcome": "Здравствуйте! Добро пожаловать в официальный премиум-бот *'Tez Mebel'*! 🛠️ ✨\n\nЗадавайте вопросы или используйте меню ниже:",
        "btn_order": "📝 Заказать / Вызов замерщика",
        "btn_catalog": "🗂 Каталог мебели",
        "btn_about": "ℹ️ О нас",
        "btn_contact": "📞 Контакты",
        "btn_change_lang": "🌐 Сменить язык",
        "btn_home": "🏠 Главная страница",
        "ask_name": "Для оформления заказа, пожалуйста, введите ваше *имя* или нажмите кнопку ниже:",
        "ask_phone": "Спасибо, {name}! Теперь отправьте ваш *номер телефона*:",
        "btn_phone": "📱 Отправить номер телефона",
        "ask_location": "Отлично! Теперь отправьте вашу *локацию* для вызова мастера:",
        "btn_location": "📍 Отправить локацию",
        "ask_furniture": "Какую мебель вы хотите заказать? Выберите или напишите свой вариант:",
        "order_done": "Спасибо! Ваш заказ принят. Наш специалист свяжется с вами в ближайшее время. 🛠️",
        "about_text": "✨ *Tez Mebel* — изготовление качественной и надежной мебели на заказ.\n\n🔹 Премиальные материалы (МДФ, Акрил, ЛДСП)\n🔹 Опытные мастера и быстрый замер\n🔹 Гарантия качества и доступные цены",
        "contact_text": "📞 *Контакты:*\n\n📞 Тел: +998 (90) 123-45-67\n📍 Адрес: г. Ташкент\n⏱ Режим работы: 09:00 - 19:00",
        "lang_changed": "Язык успешно изменен! 🇷🇺",
        "home_text": "Вы вернулись в главное меню. Выберите нужный раздел:",
        "catalog_choose": "🗂 Выберите категорию мебели:"
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
            [KeyboardButton(text=t["btn_order"]), KeyboardButton(text=t["btn_catalog"])],
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
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CATEGORIES[0]), KeyboardButton(text=CATEGORIES[1])],
            [KeyboardButton(text=CATEGORIES[2]), KeyboardButton(text=CATEGORIES[3])],
            [KeyboardButton(text=CATEGORIES[4])],
            [KeyboardButton(text=TEXTS[lang]["btn_home"])]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="➕ Katalogga mebel qo'shish")],
            [KeyboardButton(text="📁 Yozishmalarni yuklab olish"), KeyboardButton(text="📋 Buyurtmalar hisoboti")],
            [KeyboardButton(text="📢 Hammaga xabar yuborish")],
            [KeyboardButton(text="🏠 Bosh sahifa")]
        ],
        resize_keyboard=True
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
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    logging.error(f"Gemini API xatosi status kodi: {response.status}")
                    return "Kechirasiz, hozirda so'rovingizni qayta ishlashda vaqtincha xatolik yuz berdi. Iltimos, birozdan so'ng qayta yozing."
    except Exception as e:
        logging.error(f"Gemini ulanish xatosi: {e}")
        return "Tarmoqda xatolik yuz berdi. Iltimos, birozdan so'ng yana urinib ko'ring."

@dp.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
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
        "🛠 *Admin Boshqaruv Markazi*\n\nKerakli bo'limni tanlang:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

@dp.message(F.text == "📊 Statistika")
async def admin_stats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    u_count, c_count, o_count = await db_get_stats()
    stats_text = (
        f"📊 *Botning umumiy statistikasi:*\n\n"
        f"👥 Jami foydalanuvchilar: `{u_count}` ta\n"
        f"💬 Jami AI yozishmalar: `{c_count}` ta\n"
        f"📥 Jami buyurtmalar: `{o_count}` ta"
    )
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

# --- ADMIN KATEGORIYALI KATALOG QO'SHISH ---
@dp.message(F.text == "➕ Katalogga mebel qo'shish")
async def admin_add_catalog_prompt(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=CATEGORIES[0]), KeyboardButton(text=CATEGORIES[1])],
            [KeyboardButton(text=CATEGORIES[2]), KeyboardButton(text=CATEGORIES[3])],
            [KeyboardButton(text=CATEGORIES[4])],
            [KeyboardButton(text="❌ Bekor qilish")]
        ],
        resize_keyboard=True
    )
    await message.answer("📂 Mebel qaysi **kategoriyaga** tegishli ekanligini tanlang:", reply_markup=kb)
    await state.set_state(OrderState.waiting_for_cat_category)

@dp.message(OrderState.waiting_for_cat_category, F.text)
async def process_cat_category(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=get_admin_keyboard())
        return
    
    if message.text not in CATEGORIES:
        await message.answer("⚠️ Iltimos, tugmalardan birini tanlang!")
        return

    await state.update_data(cat_category=message.text)
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    await message.answer("📸 Endi mebelning **rasmini** yuboring:", reply_markup=cancel_kb)
    await state.set_state(OrderState.waiting_for_cat_photo)

@dp.message(OrderState.waiting_for_cat_photo, F.photo)
async def process_cat_photo(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    photo_id = message.photo[-1].file_id
    await state.update_data(cat_photo=photo_id)
    
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    await message.answer("📝 Endi mebelning **nomini** kiriting (masalan: *Zamonaviy oshxona*):", reply_markup=cancel_kb)
    await state.set_state(OrderState.waiting_for_cat_title)

@dp.message(OrderState.waiting_for_cat_photo)
async def process_cat_photo_invalid(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "❌ Bekor qilish":
        return
    await message.answer("⚠️ Iltimos, matn emas, aynan **mebel rasmini** yuboring!")

@dp.message(OrderState.waiting_for_cat_title, F.text)
async def process_cat_title(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=get_admin_keyboard())
        return

    await state.update_data(cat_title=message.text)
    await message.answer("📄 Endi mebelning **tavsifi va narxini** kiriting (masalan: *Material: MDF, Narxi: 2.5 mln so'm*):")
    await state.set_state(OrderState.waiting_for_cat_desc)

@dp.message(OrderState.waiting_for_cat_desc, F.text)
async def process_cat_desc(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Bekor qilindi.", reply_markup=get_admin_keyboard())
        return

    data = await state.get_data()
    category = data.get("cat_category")
    photo_id = data.get("cat_photo")
    title = data.get("cat_title")
    description = message.text

    await db_add_catalog_item(category, photo_id, title, description)
    await state.clear()
    await message.answer("✅ Rasmli mebel katalogga muvaffaqiyatli qo'shildi! 🗂", reply_markup=get_admin_keyboard())

# --- MIJOZ UCHIN KATEGORIYALI KATALOG ---
@dp.message(F.text.in_(["🗂 Mebellar katalogi", "🗂 Каталог мебели"]))
async def catalog_handler(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🍳 {CATEGORIES[0]}", callback_data="cat_Oshxona"), InlineKeyboardButton(text=f"🗄 {CATEGORIES[1]}", callback_data="cat_Shkaf")],
            [InlineKeyboardButton(text=f"🏪 {CATEGORIES[2]}", callback_data="cat_Doʻkon"), InlineKeyboardButton(text=f"💊 {CATEGORIES[3]}", callback_data="cat_Apteka")],
            [InlineKeyboardButton(text=f"🛋 {CATEGORIES[4]}", callback_data="cat_Aksessuar")]
        ]
    )
    await message.answer(TEXTS[lang]["catalog_choose"], reply_markup=inline_kb)

@dp.callback_query(F.data.startswith("cat_"))
async def category_items_handler(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    items = await db_get_catalog_items_by_category(category)
    
    if not items:
        await callback.message.answer(f"⚠️ '{category}' kategoriyasida hozircha mebellar mavjud emas.")
        await callback.answer()
        return
    
    await callback.message.answer(f"📂 *{category}* bo'yicha mebellar:", parse_mode=ParseMode.MARKDOWN)
    
    for item in items:
        item_id, photo_id, title, desc = item["id"], item["photo_id"], item["title"], item["description"]
        item_kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="📝 Shu modelga buyurtma berish", callback_data=f"order_cat_{item_id}")]]
        )
        caption_text = f"🗂 *{title}*\n\n{desc}"
        if photo_id:
            await callback.message.answer_photo(photo=photo_id, caption=caption_text, parse_mode=ParseMode.MARKDOWN, reply_markup=item_kb)
        else:
            await callback.message.answer(caption_text, parse_mode=ParseMode.MARKDOWN, reply_markup=item_kb)
    
    await callback.answer()

@dp.callback_query(F.data.startswith("order_cat_"))
async def order_from_catalog(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2])
    catalog_item = await db_get_catalog_item_by_id(item_id)
    
    if catalog_item:
        photo_id, title = catalog_item["photo_id"], catalog_item["title"]
        await state.update_data(furniture=f"Katalogdan: {title}", catalog_photo=photo_id)
    
    data = await state.get_data()
    lang = data.get("lang", "uz")
    telegram_name = callback.from_user.first_name or "Mijoz"
    
    await callback.message.answer(
        TEXTS[lang]["ask_name"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_name_keyboard(telegram_name, lang)
    )
    await state.set_state(OrderState.waiting_for_name)
    await callback.answer()

@dp.message(F.text == "📁 Yozishmalarni yuklab olish")
async def admin_download_chats_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    logs = await db_get_chat_logs()
    if not logs:
        await message.answer("Yozishmalar mavjud emas!", reply_markup=get_admin_keyboard())
        return
    
    content = "=== MIJOZ VA AI YOZISHMALARI TARIXI ===\n\n"
    for row in logs:
        content += f"Vaqt: {row['timestamp']}\nMijoz: {row['user_name']}\nSavol: {row['question']}\nAI Javob: {row['ai_answer']}\n" + "-"*40 + "\n"
    
    file_bytes = content.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename="mijozlar_yozishmalari.txt")
    await message.answer_document(document=doc, caption="📁 Barcha AI suhbatlari tarixi.", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📋 Buyurtmalar hisoboti")
async def admin_download_orders_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    orders = await db_get_orders()
    if not orders:
        await message.answer("Buyurtmalar mavjud emas!", reply_markup=get_admin_keyboard())
        return
    
    content = "=== TAHVIL QILINGAN BUYURTMALAR TARIXI ===\n\n"
    for row in orders:
        content += f"Vaqt: {row['timestamp']}\nIsm: {row['name']}\nTel: {row['phone']}\nManzil: {row['location']}\nMebel: {row['furniture']}\n" + "="*30 + "\n"
        
    file_bytes = content.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename="buyurtmalar_tarixi.txt")
    await message.answer_document(document=doc, caption="📋 Barcha buyurtmalar ro'yxati.", reply_markup=get_admin_keyboard())

@dp.message(F.text == "📢 Hammaga xabar yuborish")
async def admin_broadcast_prompt(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    cancel_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )
    await message.answer("📢 Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni kiriting:", reply_markup=cancel_kb)
    await state.set_state(OrderState.waiting_for_broadcast)

@dp.message(OrderState.waiting_for_broadcast, F.text)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("❌ Xabar tarqatish bekor qilindi.", reply_markup=get_admin_keyboard())
        return

    broadcast_text = message.text
    await state.clear()
    users = await db_get_all_users()
    
    success = 0
    fail = 0
    status_msg = await message.answer("⏳ Xabarlar tarqatilmoqda...", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

    for uid in users:
        try:
            await bot.send_message(chat_id=uid, text=f"📢 *Tez Mebel E'loni:*\n\n{broadcast_text}", parse_mode=ParseMode.MARKDOWN)
            success += 1
            await asyncio.sleep(0.03)
        except Exception:
            fail += 1

    await status_msg.edit_text(
        f"✅ Tarqatish yakunlandi!\n\n"
        f"Muvaffaqiyatli: {success} ta\n"
        f"Xatolik (bloklaganlar): {fail} ta"
    )
    await message.answer("🛠 *Admin Boshqaruv Markazi*\n\nKerakli bo'limni tanlang:", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())

@dp.message(F.text.in_(["🌐 Tilni o'zgartirish", "🌐 Сменить язык"]))
async def change_lang_handler(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await message.answer(
        "Iltimos, yangi tilni tanlang / Пожалуйста, выберите новый язык:",
        reply_markup=get_lang_keyboard()
    )
    await state.set_state(OrderState.waiting_for_lang)

@dp.message(F.text.in_(["🏠 Bosh sahifa", "🏠 Главная страница"]))
async def go_home(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("🛠 *Admin Boshqaruv Markazi*", parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
        return

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
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
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
    loc_data = {"lat": message.location.latitude, "lon": message.location.longitude} if message.location else message.text
    await state.update_data(location=loc_data)
    data = await state.get_data()
    
    if "furniture" in data and data["furniture"].startswith("Katalogdan:"):
        await finalize_order(message, state)
    else:
        lang = data.get("lang", "uz")
        await message.answer(
            TEXTS[lang]["ask_furniture"],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_furniture_keyboard(lang)
        )
        await state.set_state(OrderState.waiting_for_furniture)

@dp.message(OrderState.waiting_for_furniture, F.text)
async def process_furniture(message: Message, state: FSMContext):
    await state.update_data(furniture=message.text)
    await finalize_order(message, state)

async def finalize_order(message: Message, state: FSMContext):
    user_data = await state.get_data()
    lang = user_data.get("lang", "uz")
    
    name = user_data.get("name")
    phone = user_data.get("phone")
    location = user_data.get("location")
    furniture_detail = user_data.get("furniture", "Noma'lum")
    catalog_photo = user_data.get("catalog_photo")
    
    user_id = message.from_user.id
    username = message.from_user.username

    await db_save_order(user_id, name, phone, location, furniture_detail, catalog_photo)

    await message.answer(
        TEXTS[lang]["order_done"],
        reply_markup=get_main_keyboard(lang)
    )

    admin_text = (
        "📥 *Katalogdan yangi buyurtma qabul qilindi!*\n\n"
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
        if catalog_photo:
            await bot.send_photo(chat_id=ADMIN_ID, photo=catalog_photo, caption=admin_text, parse_mode=ParseMode.MARKDOWN, reply_markup=user_keyboard)
        else:
            await bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode=ParseMode.MARKDOWN, reply_markup=user_keyboard)

        if isinstance(location, dict):
            await bot.send_location(chat_id=ADMIN_ID, latitude=location["lat"], longitude=location["lon"])
        else:
            await bot.send_message(chat_id=ADMIN_ID, text=f"📍 *Manzil:* {location}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logging.error(f"Adminga buyurtma yuborishda xato: {e}")

    await state.set_state(None)

@dp.message(F.text.in_(["ℹ️ Biz haqimizda", "ℹ️ О нас"]))
async def about_handler(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await message.answer(TEXTS[lang]["about_text"], parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(lang))

@dp.message(F.text.in_(["📞 Aloqa", "📞 Контакты"]))
async def contact_handler(message: Message, state: FSMContext):
    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    data = await state.get_data()
    lang = data.get("lang", "uz")
    await message.answer(TEXTS[lang]["contact_text"], parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard(lang))

@dp.message(F.text)
async def ai_chat_handler(message: Message):
    if message.from_user.is_bot:
        return

    await db_add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    user = message.from_user
    name = user.full_name
    username = f"@{user.username}" if user.username else "Kiritilmagan"
    user_id = user.id
    user_text = message.text

    ai_reply = await get_gemini_response(user_text)
    await message.answer(ai_reply)

    await db_log_chat(user_id, name, user_text, ai_reply)

    user_link = f"https://t.me/{user.username}" if user.username else f"tg://user?id={user_id}"
    admin_report = (
        f"💬 *Mijoz va AI yozishmasi:*\n\n"
        f"👤 *Mijoz:* {name} ({username})\n"
        f"🆔 *ID:* `{user_id}`\n\n"
        f"❓ *Savol:* \n{user_text}\n\n"
        f"🤖 *AI Javobi:* \n{ai_reply}"
    )
    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💬 Mijozga yozish", url=user_link)]]
    )
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_report, parse_mode=ParseMode.MARKDOWN, reply_markup=admin_keyboard)
    except Exception as e:
        logging.error(f"Adminga chat yuborishda xato: {e}")

async def handle_web(request):
    return web.Response(text="Tez Mebel Premium Bot is running successfully with Supabase PostgreSQL!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    print("Bazada jadvallar tekshirilmoqda va yaratilmoqda...")
    await init_db()
    print("Tez Mebel Premium AI Boti Supabase PostgreSQL bilan to'liq ishga tushdi...")
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
