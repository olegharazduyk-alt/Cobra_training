import asyncio
import os
import psycopg2  # Переконайся, що psycopg2-binary є в requirements.txt
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

print("🔥 НОВА ВЕРСІЯ КОДУ ЗАПУСТИЛАСЯ")


# =====================
# TOKEN
# =====================

TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TOKEN") or "8716094605:AAFdtjf9xnlkniV1Cx5ikgFO6OCFevZ1nck"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# =====================
# ПІДКЛЮЧЕННЯ БАЗИ ДАНИХ
# =====================
# Якщо сервер видає None, ми беремо посилання прямо з тексту коду
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:ATzUmvoQbSJivDFWJRvrKmaFoKmlTWEY@postgres.railway.internal:5432/railway"

print(f"🔎 ПОШУК БАЗИ... Знайдено URL: {DATABASE_URL}")

if DATABASE_URL:
    try:
        # Важливо для psycopg2: міняємо postgres:// на postgresql://
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        print("🔄 Намагаюся підключитися до PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cursor = conn.cursor()
        print("✅ БАЗУ ДАНИХ УСПІШНО ПІДКЛЮЧЕНО (Postgres)!")
    except Exception as e:
        print("❌ ПОМИЛКА ПІДКЛЮЧЕННЯ ДО БД:", e)
        cursor = None
else:
    print("⚠️ КРИТИЧНА ПОМИЛКА: Базу не знайдено!")
    cursor = None
    # ==========================================
        # АВТОМАТИЧНЕ СТВОРЕННЯ ВСІХ ТАБЛИЦЬ
        # ==========================================
        
        # 1. Таблиця користувачів
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 2. Таблиця тренувань (вправи, вага, повторення)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            exercise_name TEXT,
            weight REAL,
            reps INTEGER,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # 3. Таблиця для графіку (розкладу) тренувань
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedule (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            day_of_week TEXT,
            workout_type TEXT,
            workout_time TEXT
        );
        """)
        
        conn.commit()
        print("📊 УСІ ТАБЛИЦІ УСПІШНО ПЕРЕВІРЕНО ТА СТВОРЕНО В POSTGRES!")

    except Exception as e:
        print("❌ ПОМИЛКА ПІДКЛЮЧЕННЯ АБО СТВОРЕННЯ ТАБЛИЦЬ:", e)
        cursor = None
else:
    print("⚠️ КРИТИЧНА ПОМИЛКА: Базу не знайдено!")
    cursor = None
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
# СТАРТ
# =====================
@dp.message(lambda m: m.text == "🏋️ Почати тренування")
async def start_workout(message: types.Message, state: FSMContext):
    if not cursor:
        await message.answer("❌ База не підключена")
        return

    kyiv = pytz.timezone("Europe/Kyiv")
    date = datetime.now(kyiv).strftime("%Y-%m-%d")

    cursor.execute(
        "INSERT INTO workouts (user_id, date) VALUES (%s, %s) RETURNING id",
        (message.from_user.id, date)
    )
    workout_id = cursor.fetchone()[0]
    conn.commit()

    await state.update_data(workout_id=workout_id)
    await message.answer("Обери групу:", reply_markup=category_kb)
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
        await message.answer("Введи вправу:")
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
# СЕТИ
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

    cursor.execute("""
    INSERT INTO sets (exercise_id, weight, reps, created_at)
    VALUES (%s, %s, %s, %s)
    """, (data["exercise_id"], data["weight"], int(message.text), now))
    conn.commit()

    await message.answer("Збережено ✅")
    await message.answer("Ще підхід?", reply_markup=sets_kb)
    await state.set_state(Workout.next_set)

# =====================
# ДАЛІ
# =====================
@dp.message(Workout.next_set)
async def next_set(message: types.Message, state: FSMContext):
    if message.text == "➕ Ще підхід":
        await message.answer("Введи вагу:")
        await state.set_state(Workout.weight)
    else:
        await message.answer("Додати вправу?", reply_markup=next_exercise_kb)
        await state.set_state(Workout.next_ex)

# =====================
# ЗАВЕРШЕННЯ
# =====================
@dp.message(Workout.next_ex)
async def next_ex(message: types.Message, state: FSMContext):
    if message.text == "➕ Додати вправу":
        await message.answer("Обери групу:", reply_markup=category_kb)
        await state.set_state(Workout.category)
    else:
        await message.answer("🏁 Завершено", reply_markup=menu)
        await state.clear()

# =====================
# ЗАПУСК
# =====================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
