import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8716094605:AAFdtjf9xnlkniV1Cx5ikgFO6OCFevZ1nck"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = sqlite3.connect("fitness.db")
cursor = conn.cursor()

# =====================
# БАЗА
# =====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    exercise TEXT,
    weight REAL,
    reps INTEGER,
    date TEXT
)
""")
conn.commit()

# =====================
# МЕНЮ
# =====================
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏋️ Додати тренування")],
        [KeyboardButton(text="📊 Прогрес"), KeyboardButton(text="📈 Аналіз")],
        [KeyboardButton(text="🥗 Раціон")]
    ],
    resize_keyboard=True
)

# =====================
# ВПРАВИ
# =====================
exercise_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Жим лежачи"), KeyboardButton(text="Присід")],
        [KeyboardButton(text="Станова тяга"), KeyboardButton(text="Підтягування")],
        [KeyboardButton(text="Жим гантелей"), KeyboardButton(text="Біцепс")],
        [KeyboardButton(text="Трицепс"), KeyboardButton(text="Плечі")],
        [KeyboardButton(text="Жим ногами"), KeyboardButton(text="Розводка")],
        [KeyboardButton(text="Тяга верхнього блока"), KeyboardButton(text="Тяга нижнього блока")],
        [KeyboardButton(text="Французький жим"), KeyboardButton(text="Молотки")],
        [KeyboardButton(text="Планка"), KeyboardButton(text="Скручування")],
        [KeyboardButton(text="Віджимання"), KeyboardButton(text="Бруси")],
        [KeyboardButton(text="Інша")]
    ],
    resize_keyboard=True
)

# =====================
# FSM
# =====================
class AddWorkout(StatesGroup):
    exercise = State()
    custom_exercise = State()
    weight = State()
    reps = State()

# =====================
# START
# =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привіт 💪", reply_markup=menu)

# =====================
# ДОДАТИ
# =====================
@dp.message(lambda m: m.text == "🏋️ Додати тренування")
async def add_start(message: types.Message, state: FSMContext):
    await message.answer("Обери вправу:", reply_markup=exercise_kb)
    await state.set_state(AddWorkout.exercise)

@dp.message(AddWorkout.exercise)
async def get_exercise(message: types.Message, state: FSMContext):
    if message.text == "Інша":
        await message.answer("Введи назву вправи:")
        await state.set_state(AddWorkout.custom_exercise)
    else:
        await state.update_data(exercise=message.text)
        await message.answer("Введи вагу (кг):")
        await state.set_state(AddWorkout.weight)

@dp.message(AddWorkout.custom_exercise)
async def custom_exercise(message: types.Message, state: FSMContext):
    await state.update_data(exercise=message.text)
    await message.answer("Введи вагу (кг):")
    await state.set_state(AddWorkout.weight)

@dp.message(AddWorkout.weight)
async def get_weight(message: types.Message, state: FSMContext):
    await state.update_data(weight=float(message.text))
    await message.answer("Введи повторення:")
    await state.set_state(AddWorkout.reps)

@dp.message(AddWorkout.reps)
async def get_reps(message: types.Message, state: FSMContext):
    data = await state.get_data()

    cursor.execute("""
    INSERT INTO workouts (user_id, exercise, weight, reps, date)
    VALUES (?, ?, ?, ?, ?)
    """, (
        message.from_user.id,
        data["exercise"],
        data["weight"],
        int(message.text),
        datetime.now().strftime("%Y-%m-%d")
    ))
    conn.commit()

    await message.answer("✅ Додано", reply_markup=menu)
    await state.clear()

# =====================
# ПРОГРЕС (ПО ДНЯХ)
# =====================
@dp.message(lambda m: m.text == "📊 Прогрес")
async def progress(message: types.Message):
    cursor.execute("""
    SELECT date, exercise, weight, reps 
    FROM workouts 
    WHERE user_id=? 
    ORDER BY date DESC
    """, (message.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await message.answer("❌ Даних немає")
        return

    text = "📊 Тренування :\n\n"
    current_date = None

    for date, ex, w, r in rows:
        if date != current_date:
            current_date = date
            text += f"\n📅 {date}:\n"

        text += f"  {ex} | {w} кг | {r}\n"

    await message.answer(text)

# =====================
# АНАЛІЗ (МІЖ ДНЯМИ)
# =====================
@dp.message(lambda m: m.text == "📈 Аналіз")
async def analysis(message: types.Message):
    cursor.execute("""
    SELECT date, exercise, weight 
    FROM workouts 
    WHERE user_id=? 
    ORDER BY date
    """, (message.from_user.id,))

    rows = cursor.fetchall()

    if len(rows) < 2:
        await message.answer("❌ Мало даних")
        return

    # групування по днях
    days = {}
    for date, ex, w in rows:
        days.setdefault(date, {})
        days[date][ex] = w

    dates = list(days.keys())

    if len(dates) < 2:
        await message.answer("❌ Потрібно мінімум 2 дні тренувань")
        return

    last_day = days[dates[-1]]
    prev_day = days[dates[-2]]

    text = f"📈 Прогрес ({dates[-2]} → {dates[-1]}):\n\n"

    for ex in last_day:
        if ex in prev_day:
            diff = last_day[ex] - prev_day[ex]

            if diff > 0:
                text += f"{ex}: +{diff} кг 🔥\n"
            elif diff < 0:
                text += f"{ex}: {diff} кг 📉\n"
            else:
                text += f"{ex}: без змін\n"

    await message.answer(text)

# =====================
# РАЦІОН
# =====================
@dp.message(lambda m: m.text == "🥗 Раціон")
async def diet(message: types.Message):
    await message.answer("Введи: вага режим\nНаприклад: 70 маса")

@dp.message(lambda m: "маса" in m.text or "сушка" in m.text)
async def calc_diet(message: types.Message):
    try:
        parts = message.text.split()
        weight = float(parts[0])
        mode = parts[1]

        calories = weight * 30
        if mode == "маса":
            calories += 400
        else:
            calories -= 400

        protein = weight * 2
        fat = weight * 1
        carbs = (calories - (protein*4 + fat*9)) / 4

        await message.answer(
            f"🔥 Калорії: {int(calories)}\n"
            f"🥩 Білки: {int(protein)} г\n"
            f"🥑 Жири: {int(fat)} г\n"
            f"🍚 Вуглеводи: {int(carbs)} г"
        )
    except:
        await message.answer("Формат: 70 маса")

# =====================
# ЗАПУСК
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
