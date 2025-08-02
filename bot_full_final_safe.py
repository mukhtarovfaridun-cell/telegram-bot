import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime
import aiosqlite

TOKEN = '8464032030:AAFo-AbD5Qctp-_R4Q_5faoJmZuORBM5OXw'
OPERATORS = {
    5852708803: "Фаридун",
    8029013327: "Мохира",
    333333333: "Саша",
    444444444: "Камол",
    555555555: "Махмуд",
    666666666: "Улугбек"
}
CASHIER = 932884291
DIRECTOR = 305356086

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class OrderForm(StatesGroup):
    fio = State()
    passport = State()
    amount = State()
    comment = State()
    sale_type = State()
    waiting_amount = State()

async def init_db():
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT,
                operator_id INTEGER,
                fio TEXT,
                passport TEXT,
                amount REAL,
                paid_amount REAL DEFAULT 0,
                type TEXT,
                comment TEXT,
                status TEXT DEFAULT 'pending',
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def generate_order_number():
    now = datetime.now()
    short = now.strftime("%m%d%H%M")
    return f"#{short}"

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    if message.from_user.id in OPERATORS:
        kb.add("🆕 Новый заказ", "📊 Отчет")
    elif message.from_user.id in [CASHIER, DIRECTOR]:
        kb.add("📊 Отчет", "📋 Должники")
    else:
        return await message.answer("Нет доступа.")
    await message.answer("Добро пожаловать", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "🆕 Новый заказ")
async def new_order(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("Введите ФИО:")
    await OrderForm.fio.set()

@dp.message_handler(state=OrderForm.fio)
async def step_fio(message: types.Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await message.answer("Введите серию паспорта:")
    await OrderForm.passport.set()

@dp.message_handler(state=OrderForm.passport)
async def step_passport(message: types.Message, state: FSMContext):
    await state.update_data(passport=message.text)
    await message.answer("Введите сумму:")
    await OrderForm.amount.set()

@dp.message_handler(state=OrderForm.amount)
async def step_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip().replace('$', ''))
        await state.update_data(amount=amount)
        await message.answer("Введите комментарий (или - если нет):")
        await OrderForm.comment.set()
    except:
        await message.answer("❗ Неверная сумма. Попробуйте снова.")

@dp.message_handler(state=OrderForm.comment)
async def step_comment(message: types.Message, state: FSMContext):
    await state.update_data(comment=message.text)
    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("Продажа", callback_data="Продажа"),
        InlineKeyboardButton("Возврат", callback_data="Возврат")
    )
    await message.answer("Выберите тип:", reply_markup=kb)
    await OrderForm.sale_type.set()

@dp.callback_query_handler(state=OrderForm.sale_type)
async def finish_order(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    order_number = await generate_order_number()
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""INSERT INTO orders 
        (order_number, operator_id, fio, passport, amount, type, comment) 
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (order_number, call.from_user.id, data['fio'], data['passport'], data['amount'], call.data, data['comment']))
        await db.commit()

    text = (
        f"📦 Заказ {order_number}\n"
        f"👤 Оператор: {OPERATORS.get(call.from_user.id, call.from_user.id)}\n"
        f"ФИО: {data['fio']}\n"
        f"Паспорт: {data['passport']}\n"
        f"Сумма: {data['amount']}$\n"
        f"Тип: {call.data}\n"
        f"Комментарий: {data['comment']}"
    )

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("✅ Оплачено", callback_data=f"pay_full_{order_number}"),
        InlineKeyboardButton("💵 Частично", callback_data=f"pay_partial_{order_number}")
    )

    await bot.send_message(CASHIER, text, reply_markup=kb)
    await call.message.answer("Заказ отправлен кассиру.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("pay_full_"))
async def full_payment(call: types.CallbackQuery):
    order_number = call.data.split("_")[-1]
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("UPDATE orders SET status = 'paid', paid_amount = amount, timestamp = ? WHERE order_number = ?",
                         (datetime.now().isoformat(sep=' ', timespec='seconds'), order_number))
        cursor = await db.execute("SELECT operator_id, fio, passport, amount FROM orders WHERE order_number = ?", (order_number,))
        row = await cursor.fetchone()
    if row:
        op_id, fio, passport, amount = row
        await bot.send_message(op_id, f"✅ Оплата по заказу {order_number} получена полностью:\nФИО: {fio}\nПаспорт: {passport}\nСумма: {amount}$")
        await call.message.edit_reply_markup()

@dp.callback_query_handler(lambda c: c.data.startswith("pay_partial_"))
async def ask_partial(call: types.CallbackQuery, state: FSMContext):
    order_number = call.data.split("_")[-1]
    await state.update_data(order_number=order_number)
    await call.message.answer("Введите сумму, которую оплатили:")
    await OrderForm.waiting_amount.set()
    await call.message.edit_reply_markup()

@dp.message_handler(state=OrderForm.waiting_amount)
async def handle_partial(message: types.Message, state: FSMContext):
    try:
        partial = float(message.text.strip().replace('$', ''))
    except:
        return await message.answer("❗ Неверная сумма.")
    data = await state.get_data()
    order_number = data["order_number"]

    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("SELECT paid_amount, amount, operator_id, fio, passport FROM orders WHERE order_number = ?", (order_number,))
        row = await cursor.fetchone()
        if not row:
            return await message.answer("❌ Заказ не найден.")
        paid_before, total_amount, op_id, fio, passport = row
        new_total = paid_before + partial
        status = 'partial' if new_total < total_amount else 'paid'
        await db.execute("UPDATE orders SET paid_amount = ?, status = ?, timestamp = ? WHERE order_number = ?",
                         (new_total, status, datetime.now().isoformat(sep=' ', timespec='seconds'), order_number))
        await db.commit()

    remain = total_amount - new_total
    await bot.send_message(op_id,
        f"💵 Частичная оплата по заказу {order_number}:\n"
        f"ФИО: {fio}\nПаспорт: {passport}\n"
        f"Получено: {partial}$\nОстаток: {remain:.2f}$"
    )
    await message.answer(f"Записано. Остаток: {remain:.2f}$")
    await state.finish()

@dp.message_handler(lambda m: m.text == "📊 Отчет")
async def report_handler(message: types.Message):
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("""
            SELECT operator_id, SUM(amount), SUM(paid_amount), COUNT(*) FROM orders GROUP BY operator_id
        """)
        rows = await cursor.fetchall()
    msg = "📊 Отчет по операторам:\n"
    for op_id, total, paid, count in rows:
        msg += f"{OPERATORS.get(op_id, op_id)}: заказов {count}, оплачено {paid:.2f}$ / {total:.2f}$\n"
    await message.answer(msg)

@dp.message_handler(lambda m: m.text == "📋 Должники")
async def debtors(message: types.Message):
    async with aiosqlite.connect("orders.db") as db:
        cursor = await db.execute("""
            SELECT order_number, fio, passport, amount, paid_amount FROM orders 
            WHERE status != 'paid'
            ORDER BY timestamp DESC
        """)
        rows = await cursor.fetchall()
    if not rows:
        return await message.answer("✅ Нет долгов.")
    text = "📋 Список должников:\n"
    for o, fio, psp, amt, paid in rows:
        text += f"{o}: {fio} ({psp}) — Оплачено: {paid}$ / {amt}$\n"
    await message.answer(text)

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    import os
    import logging
    from aiogram import Bot

    # Настройка логов
    logging.basicConfig(level=logging.INFO)

    # Получаем токен из переменных окружения
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        raise ValueError("⛔ Переменная окружения TELEGRAM_TOKEN не задана")

    # Инициализация бота и диспетчера заново с безопасным токеном
    bot = Bot(token=TOKEN)
    dp = Dispatcher(bot, storage=MemoryStorage())

    # Запускаем цикл
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())
    dp.run_polling(bot)
