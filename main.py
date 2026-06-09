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
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://postgres:ATzUmvoQbSJivDFWJRvrKmaFoKmlTWEY@postgres.railway.internal:5432/railway"

print(f"🔎 ПОШУК БАЗИ... Знайдено URL: {DATABASE_URL}")

conn = None
cursor = None

if DATABASE_URL:
    try:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        
        print("🔄 Намагаюся підключитися до PostgreSQL...")
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cursor = conn.cursor()
        print("✅ БАЗУ ДАНИХ УСПІШНО ПІДКЛЮЧЕНО (Postgres)!")
        
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
        
        # 2. Таблиця тренувань
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            date TEXT
        );
        """)
        
        # 3. Таблиця логів вправ
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS exercises_log (
            id SERIAL PRIMARY KEY,
            workout_id INTEGER,
            name TEXT,
            category TEXT
        );
        """)
        
        # 4. Таблиця підходів
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            id SERIAL PRIMARY KEY,
            exercise_id INTEGER,
            weight REAL,
            reps INTEGER,
            created_at TIMESTAMP
        );
        """)
        
        # 5. Таблиця для графіку тренувань
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
    if cursor:
        try:
            cursor.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (message.from_user.id, message.from_user.username)
            )
            conn.commit()
        except Exception as e:
            print(f"Помилка додавання користувача: {e}")
            
    await message.answer("Привіт 💪", reply_markup=menu)

# =====================
# СТАРТ ТРЕНУВАННЯ
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
