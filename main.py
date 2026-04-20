import asyncio
import os
import psycopg2
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = "8716094605:AAFdtjf9xnlkniV1Cx5ikgFO6OCFevZ1nck"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cursor = conn.cursor()

# =====================
# БАЗА
# =====================
cursor.execute("""
CREATE TABLE IF NOT EXISTS workouts (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS exercises_log (
    id SERIAL PRIMARY KEY,
    workout_id INTEGER,
    name TEXT,
    category TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sets (
    id SERIAL PRIMARY KEY,
    exercise_id INTEGER,
    weight REAL,
    reps INTEGER,
    created_at TIMESTAMP
)
""")
conn.commit()

# =====================
# МЕНЮ
# =====================
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏋️ Почати тренування")],
        [KeyboardButton(text="📊 Прогрес"), KeyboardButton(text="📈 Аналіз")],
        [KeyboardButton(text="🥗 Раціон")]
    ],
    resize_keyboard=True
)

category_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Ноги"), KeyboardButton(text="Руки")],
        [KeyboardButton(text="Груди"), KeyboardButton(text="Спина")],
        [KeyboardButton(text="Плечі")]
    ],
    resize_keyboard=True
)

sets_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Ще підхід")],
        [KeyboardButton(text="✅ Завершити вправу")]
    ],
    resize_keyboard=True
)

next_exercise_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Додати вправу")],
        [KeyboardButton(text="🏁 Завершити тренування")]
    ],
    resize_keyboard=True
)

exercises = {
    "Ноги": ["Присід", "Жим ногами"],
    "Руки": ["Біцепс", "Трицепс"],
    "Груди": ["Жим лежачи", "Віджимання"],
    "Спина": ["Станова тяга", "Підтягування"],
    "Плечі": ["Жим плечима"]
}

# =====================
# FSM
# =====================
class Workout(StatesGroup):
    category = State()
    exercise = State()
    custom = State()
    weight = State()
    reps = State()
    next_set = State()
    next_ex = State()

# =====================
# START
# =====================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привіт 💪", reply_markup=menu)

# =====================
# СТАРТ ТРЕНУВАННЯ
# =====================
@dp.message(lambda m: m.text == "🏋️ Почати тренування")
async def start_workout(message: types.Message, state: FSMContext):
    kyiv = pytz.timezone("Europe/Kyiv")
    date = datetime.now(kyiv).strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO workouts (user_id, date) VALUES (%s, %s) RETURNING id",
        (message.from_user.id, date)
    )
    workout_id = cursor.fetchone()[0]
    conn.commit()

    await state.update_data(workout_id=workout_id)
    await message.answer("Обери групу м'язів:", reply_markup=category_kb)
    await state.set_state(Workout.category)

# =====================
# КАТЕГОРІЯ
# =====================
@dp.message(Workout.category)
async def choose_category(message: types.Message, state: FSMContext):
    category = message.text
    await state.update_data(category=category)

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=x)] for x in exercises.get(category, [])] + [[KeyboardButton(text="Інша")]],
        resize_keyboard=True
    )

    await message.answer("Обери вправу:", reply_markup=kb)
    await state.set_state(Workout.exercise)

# =====================
# ВПРАВА
# =====================
@dp.message(Workout.exercise)
async def choose_exercise(message: types.Message, state: FSMContext):
    if message.text == "Інша":
        await message.answer("Введи свою вправу:")
        await state.set_state(Workout.custom)
    else:
        await state.update_data(exercise=message.text)
        await create_exercise(message, state)

@dp.message(Workout.custom)
async def custom_ex(message: types.Message, state: FSMContext):
    await state.update_data(exercise=message.text)
    await create_exercise(message, state)

async def create_exercise(message, state):
    data = await state.get_data()

    cursor.execute("""
    INSERT INTO exercises_log (workout_id, name, category)
    VALUES (%s, %s, %s) RETURNING id
    """, (data["workout_id"], data["exercise"], data["category"]))

    ex_id = cursor.fetchone()[0]
    conn.commit()

    await state.update_data(exercise_id=ex_id)

    await message.answer("Введи вагу:")
    await state.set_state(Workout.weight)

# =====================
# SETS + ЛОГІКА
# =====================
@dp.message(Workout.weight)
async def weight(message: types.Message, state: FSMContext):
    await state.update_data(weight=float(message.text))
    await message.answer("Введи повторення:")
    await state.set_state(Workout.reps)

@dp.message(Workout.reps)
async def reps(message: types.Message, state: FSMContext):
    data = await state.get_data()

    kyiv = pytz.timezone("Europe/Kyiv")
    now = datetime.now(kyiv)

    weight = data["weight"]
    reps_val = int(message.text)

    # запис сету
    cursor.execute("""
    INSERT INTO sets (exercise_id, weight, reps, created_at)
    VALUES (%s, %s, %s, %s)
    """, (data["exercise_id"], weight, reps_val, now))
    conn.commit()

    # PR
    cursor.execute("SELECT MAX(weight) FROM sets WHERE exercise_id=%s", (data["exercise_id"],))
    max_weight = cursor.fetchone()[0]

    text = ""

    if weight == max_weight:
        text += "🏆 Новий максимум!\n"

    # рекомендації
    if reps_val >= 16:
        text += "📈 Збільш вагу (+2.5–5 кг)\n"
    elif reps_val <= 5:
        text += "⚠️ Вже важко\n"
    else:
        text += "👍 Добре\n"

    # відпочинок
    cursor.execute("""
    SELECT created_at FROM sets
    WHERE exercise_id=%s
    ORDER BY created_at DESC LIMIT 2
    """, (data["exercise_id"],))

    times = cursor.fetchall()

    if len(times) == 2:
        diff = (times[0][0] - times[1][0]).total_seconds()

        if diff < 60:
            text += "⚠️ <1 хв відпочинку\n"
        elif diff < 120:
            text += "👍 норм відпочинок\n"
        else:
            text += "💪 добре\n"

    await message.answer(text)

    await message.answer("Ще підхід?", reply_markup=sets_kb)
    await state.set_state(Workout.next_set)

# =====================
# ДАЛІ СЕТИ
# =====================
@dp.message(Workout.next_set)
async def next_set(message: types.Message, state: FSMContext):
    if message.text == "➕ Ще підхід":
        await message.answer("Введи вагу:")
        await state.set_state(Workout.weight)
    else:
        await message.answer("Додати ще вправу?", reply_markup=next_exercise_kb)
        await state.set_state(Workout.next_ex)

# =====================
# НАСТУПНА ВПРАВА
# =====================
@dp.message(Workout.next_ex)
async def next_ex(message: types.Message, state: FSMContext):
    if message.text == "➕ Додати вправу":
        await message.answer("Обери групу:", reply_markup=category_kb)
        await state.set_state(Workout.category)
    else:
        await message.answer("🏁 Тренування завершено", reply_markup=menu)
        await state.clear()

# =====================
# ПРОГРЕС
# =====================
@dp.message(lambda m: m.text == "📊 Прогрес")
async def progress(message: types.Message):
    cursor.execute("""
    SELECT e.name, s.weight, s.reps
    FROM sets s
    JOIN exercises_log e ON s.exercise_id = e.id
    JOIN workouts w ON e.workout_id = w.id
    WHERE w.user_id=%s
    ORDER BY s.created_at DESC
    LIMIT 10
    """, (message.from_user.id,))

    rows = cursor.fetchall()

    text = "📊 Останні підходи:\n\n"
    for r in rows:
        text += f"{r[0]} | {r[1]} кг | {r[2]}\n"

    await message.answer(text)

# =====================
# АНАЛІЗ
# =====================
@dp.message(lambda m: m.text == "📈 Аналіз")
async def analysis(message: types.Message):
    cursor.execute("""
    SELECT e.name, MAX(s.weight), AVG(s.weight), COUNT(s.id)
    FROM sets s
    JOIN exercises_log e ON s.exercise_id = e.id
    JOIN workouts w ON e.workout_id = w.id
    WHERE w.user_id=%s
    GROUP BY e.name
    """, (message.from_user.id,))

    rows = cursor.fetchall()

    if not rows:
        await message.answer("❌ Немає даних")
        return

    text = "📈 Аналіз:\n\n"

    for name, max_w, avg_w, count in rows:
        text += (
            f"{name}\n"
            f"🏆 Макс: {round(max_w,1)} кг\n"
            f"📊 Середня: {round(avg_w,1)} кг\n"
            f"🔁 Підходів: {count}\n\n"
        )

    await message.answer(text)

# =====================
# РАЦІОН
# =====================
from aiogram.fsm.context import FSMContext
@dp.message(lambda m: m.text == "🥗 Раціон")
async def diet(message: types.Message, state: FSMContext):
    await state.clear()  # 🔥 ВИХІД З БУДЬ-ЯКОГО СТАНУ
    await message.answer("Введи: 70 маса або 70 сушка")


@dp.message(lambda m: len(m.text.split()) == 2)
async def calc_diet(message: types.Message, state: FSMContext):
    try:
        parts = message.text.lower().split()
        weight = float(parts[0])
        mode = parts[1]

        if mode not in ["маса", "сушка"]:
            return

        # 🔥 теж на всякий випадок очищаємо стан
        await state.clear()

        calories = weight * 30 + (400 if mode == "маса" else -400)
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
        await message.answer("❌ Формат: 70 маса")

# =====================
# ЗАПУСК
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
