import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from database import add_default_products, init_db

# ⚙️ Sizning tokeningiz va ID raqamingiz kiritildi:
TOKEN = "8708329718:AAETLtIatPvg6DvfrP5Zf9EtqMLu4Czf3RA"
ADMIN_ID = 1927054009

router = Router()
carts = {}

# FSM Holatlari
class OrderState(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_address = State()
    waiting_for_receipt = State()


# --- ASOSIY MENYU ---
@router.message(F.text == "/start")
async def cmd_start(message: Message):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗂 Mebellar katalogi"), KeyboardButton(text="🛒 Savatcha")],
            [KeyboardButton(text="📞 Biz bilan aloqa"), KeyboardButton(text="📦 Mening buyurtmalarim")],
        ],
        resize_keyboard=True,
    )
    if message.from_user.id == ADMIN_ID:
        markup.keyboard.append([KeyboardButton(text="👑 Admin Panel")])

    await message.answer(
        "✨ **"Tez Mebel"** rasmiy botiga xush kelibsiz!\nSifatli mebellar va qulay to'plamlarni tanlang:",
        reply_markup=markup,
        parse_mode="Markdown"
    )


# --- KATALOG ---
@router.message(F.text == "🗂 Mebellar katalogi")
async def show_catalog(message: Message):
    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description, price FROM products")
    products = cursor.fetchall()
    conn.close()

    if not products:
        await message.answer("Hozircha katalogda mahsulotlar yo'q.")
        return

    for prod_id, name, desc, price in products:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Savatchaga qo'shish", callback_data=f"add_{prod_id}")]
        ])
        await message.answer(
            f"🪑 **{name}**\n\n📄 {desc}\n💰 **Narxi:** {price:,.0f} so'm",
            reply_markup=kb,
            parse_mode="Markdown"
        )


@router.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    if user_id not in carts:
        carts[user_id] = []
    carts[user_id].append(prod_id)

    await callback.answer("Mahsulot savatchaga qo'shildi! ✅")


# --- SAVATCHA ---
@router.message(F.text == "🛒 Savatcha")
async def show_cart(message: Message):
    user_id = message.from_user.id
    user_cart = carts.get(user_id, [])

    if not user_cart:
        await message.answer("Savatchangiz bo'sh 📭")
        return

    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()

    total = 0
    text = "🛒 **Sizning savatchangiz:**\n\n"
    for prod_id in user_cart:
        cursor.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,))
        prod = cursor.fetchone()
        if prod:
            text += f"▪️ {prod[0]} — {prod[1]:,.0f} so'm\n"
            total += prod[1]
    conn.close()

    text += f"\n💰 **Jami summa:** {total:,.0f} so'm"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Buyurtmani rasmiylashtirish", callback_data="checkout")],
        [InlineKeyboardButton(text="🗑 Savatchani tozalash", callback_data="clear_cart")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    carts[callback.from_user.id] = []
    await callback.message.edit_text("Savatcha tozalandi 🗑")
    await callback.answer()


# --- BUYURTMA RASMIYLASHTIRISH (FSM) ---
@router.callback_query(F.data == "checkout")
async def start_checkout(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Iltimos, ism va familiyangizni kiriting:")
    await state.set_state(OrderState.waiting_for_name)
    await callback.answer()


@router.message(OrderState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=kb)
    await state.set_state(OrderState.waiting_for_phone)


@router.message(OrderState.waiting_for_phone, F.contact)
async def process_phone(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Geolyatsiyani yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer("Yetkazib berish manzilini (geolyatsiya orqali) yuboring:", reply_markup=kb)
    await state.set_state(OrderState.waiting_for_address)


@router.message(OrderState.waiting_for_address, F.location)
async def process_address(message: Message, state: FSMContext):
    lat, lon = message.location.latitude, message.location.longitude
    address = f"Koordinatalar: {lat}, {lon}"
    await state.update_data(address=address)

    data = await state.get_data()
    user_id = message.from_user.id

    user_cart = carts.get(user_id, [])
    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()
    total = 0
    for pid in user_cart:
        cursor.execute("SELECT price FROM products WHERE id = ?", (pid,))
        res = cursor.fetchone()
        if res:
            total += res[0]

    cursor.execute(
        "INSERT INTO orders (user_id, fullname, phone, address, total_price, status) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, data['name'], data['phone'], data['address'], total, "To'lov kutilmoqda")
    )
    conn.commit()
    conn.close()

    carts[user_id] = []

    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 To'lovni qildim (Chek yuborish)", callback_data="send_receipt")]
    ])

    await message.answer(
        f"⏳ **Toʻlov kutilmoqda.**\n\n"
        f"Buyurtma summasi: **{total:,.0f} so'm**\n"
        f"Karta raqami: `8600 0000 0000 0000` (Tez Mebel)\n\n"
        f"To'lovni amalga oshirgach, chekni yuborish uchun quyidagi tugmani bosing:",
        reply_markup=pay_kb,
        parse_mode="Markdown"
    )
    await state.clear()


# --- TO'LOV ISBOTI (CHEK) ---
@router.callback_query(F.data == "send_receipt")
async def ask_receipt(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📸 Iltimos, toʻlovni tasdiqlovchi **chek rasmini (skrinshot)** yuboring:")
    await state.set_state(OrderState.waiting_for_receipt)
    await callback.answer()


@router.message(OrderState.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    user_id = message.from_user.id

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (Jarayon boshlandi)", callback_data=f"pay_yes_{user_id}"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"pay_no_{user_id}")
        ]
    ])

    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo_id,
        caption=f"🔔 **Yangi toʻlov isboti keldi!**\nFoydalanuvchi ID: `{user_id}`",
        reply_markup=admin_kb,
        parse_mode="Markdown"
    )
    await message.answer("✅ Chek adminga yuborildi. Tekshirilmoqda, iltimos kuting...")
    await state.clear()


# --- ADMIN BOSHQARUVI (STATUSLAR) ---
@router.callback_query(F.data.startswith("pay_"))
async def admin_decision(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    action = parts[1]
    user_id = int(parts[2])

    conn = sqlite3.connect("tez_mebel.db")
    cursor = conn.cursor()

    if action == "yes":
        cursor.execute("UPDATE orders SET status = 'Jarayon boshlandi' WHERE user_id = ?", (user_id,))
        conn.commit()

        await bot.send_message(
            chat_id=user_id,
            text="🎉 **Toʻlovingiz tasdiqlandi!**\n\n🚀 Buyurtmangiz tayyorlanish boʻyicha **jarayon boshlandi**.",
            parse_mode="Markdown"
        )
        await callback.message.edit_caption(caption=callback.message.caption + "\n\nSTATUS: ✅ Jarayon boshlandi")
        await callback.answer("Tasdiqlandi va mijozga xabar yuborildi!")
    else:
        cursor.execute("UPDATE orders SET status = 'Buyurtma bekor boʻldi' WHERE user_id = ?", (user_id,))
        conn.commit()

        await bot.send_message(
            chat_id=user_id,
            text="❌ **Buyurtma bekor boʻldi.**\n\nAfsuski, toʻlovingiz tasdiqlanmadi yoki chek yaroqsiz deb topildi.",
            parse_mode="Markdown"
        )
        await callback.message.edit_caption(caption=callback.message.caption + "\n\nSTATUS: ❌ Buyurtma bekor boʻldi")
        await callback.answer("Buyurtma bekor qilindi.")
    conn.close()


# --- ADMIN PANEL ---
@router.message(F.text == "👑 Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Buyurtmalar statistikasi")],
            [KeyboardButton(text="🔙 Asosiy menyu")],
        ],
        resize_keyboard=True,
    )
    await message.answer("Xush kelibsiz, Admin! Kerakli bo'limni tanlang:", reply_markup=kb)


@router.message(F.text == "🔙 Asosiy menyu")
async def back_to_main(message: Message):
    await cmd_start(message)


# --- ISHGA TUSHIRISH ---
async def main():
    init_db()
    add_default_products()

    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("Tez Mebel boti to'liq ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
