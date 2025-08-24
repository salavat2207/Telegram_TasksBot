import asyncio
import datetime
import logging
import os
import sqlite3
import sys
import random

from aiogram.fsm.context import FSMContext
from actions import get_random_task

import aiogram
from aiogram.utils.keyboard import InlineKeyboardBuilder  # (можешь удалить, если не нужен)
from dotenv import load_dotenv
from pathlib import Path

from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State

load_dotenv(Path(__file__).parent / ".env")
TOKEN = os.getenv("TOKEN")

dp = Dispatcher()

# ========== БД и утилиты ==========
DB_PATH = Path(__file__).with_name("base.db")

def db():
    return sqlite3.connect(DB_PATH)

def ensure_schema():
    con = db(); cur = con.cursor()

    # users (как было)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER UNIQUE NOT NULL,
        username TEXT,
        score INTEGER NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # миграции для users (как было)
    cur.execute("PRAGMA table_info(users)")
    cols = {r[1] for r in cur.fetchall()}
    if "username" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "score" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN score INTEGER NOT NULL DEFAULT 0")

    # NEW: таблица задач
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        language TEXT NOT NULL,       -- 'python' / 'javascript'
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        hint TEXT
    )
    """)

    # NEW: таблица очков по дням (если уже добавлял — оставь)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER NOT NULL,
        date TEXT NOT NULL,            -- YYYY-MM-DD
        score INTEGER NOT NULL DEFAULT 0,
        UNIQUE(tg_id, date)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_scores_tg_date ON scores(tg_id, date)")

    con.commit(); con.close()



def today_iso() -> str:
    # локальная дата ОС; если хочешь строго Europe/Berlin — можно использовать pytz/zoneinfo
    return datetime.date.today().isoformat()

def add_score_today_and_get_total(tg_id: int, delta: int) -> int:
    """Прибавить delta к сегодняшним очкам и вернуть итог за сегодня."""
    con = db(); cur = con.cursor()
    d = today_iso()
    cur.execute("""
        INSERT INTO scores (tg_id, date, score)
        VALUES (?, ?, ?)
        ON CONFLICT(tg_id, date) DO UPDATE SET score = score + excluded.score
    """, (tg_id, d, delta))
    # опционально — копим «всего за всё время» в users.score:
    cur.execute("UPDATE users SET score = score + ? WHERE tg_id = ?", (delta, tg_id))
    # вернуть сегодняшнее значение
    cur.execute("SELECT score FROM scores WHERE tg_id = ? AND date = ?", (tg_id, d))
    row = cur.fetchone()
    con.commit(); con.close()
    return int(row[0]) if row else 0

def get_today_score(tg_id: int) -> int:
    con = db(); cur = con.cursor()
    cur.execute("SELECT score FROM scores WHERE tg_id = ? AND date = ?", (tg_id, today_iso()))
    row = cur.fetchone(); con.close()
    return int(row[0]) if row else 0

def get_total_score_all_time(tg_id: int) -> int:
    """Если хочешь показывать общий счёт: суммируем из таблицы scores."""
    con = db(); cur = con.cursor()
    cur.execute("SELECT COALESCE(SUM(score), 0) FROM scores WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone(); con.close()
    return int(row[0]) if row and row[0] is not None else 0


def ensure_user(tg_id: int, username: str | None):
    con = db()
    cur = con.cursor()
    # UPSERT
    cur.execute("""
        INSERT INTO users (tg_id, username, score)
        VALUES (?, ?, 0)
        ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username
    """, (tg_id, username))
    con.commit()

    # мягкая проверка (без падения)
    cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT OR IGNORE INTO users (tg_id, username, score) VALUES (?, ?, 0)", (tg_id, username))
        cur.execute("UPDATE users SET username = COALESCE(?, username) WHERE tg_id = ?", (username, tg_id))
        con.commit()
        cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
        row = cur.fetchone()
        if not row:
            print(f"[WARN] ensure_user: still not found tg_id={tg_id}, DB={DB_PATH.resolve()}")

    con.close()


async def main() -> None:
    ensure_schema()  # <= добавь это
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)



def add_score_and_get_total(tg_id: int, delta: int) -> int:
    """Прибавить очки и вернуть итоговый счёт."""
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET score = score + ? WHERE tg_id = ?", (delta, tg_id))
    cur.execute("SELECT score FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    con.commit()
    con.close()
    return int(row[0]) if row else 0

def get_user_score(tg_id: int) -> int:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT score FROM users WHERE tg_id = ?", (tg_id,))
    row = cur.fetchone()
    con.close()
    return int(row[0]) if row else 0

# ========== Состояния ==========
class QuizState(StatesGroup):
    language = State()

class AnswerState(StatesGroup):
    waiting_for_answer = State()

# ========== Хелперы UI ==========
def get_language_keyboard():
    kb = [
        [KeyboardButton(text="Python")],
        [KeyboardButton(text="JavaScript")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_action_keyboard():
    kb = [
        [KeyboardButton(text="Получить вопрос")],
        [KeyboardButton(text="Узнать свой счет")],
        [KeyboardButton(text="К выбору языка")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ========== Хендлеры ==========
@dp.message(CommandStart())
async def comand_start_handler(message: Message):
    ensure_schema()
    ensure_user(message.from_user.id, message.from_user.username)

    today_total = get_today_score(message.from_user.id)  # 👈 СЕГОДНЯ
    # если нужен общий счёт по всем дням:
    # all_time = get_total_score_all_time(message.from_user.id)

    await message.answer(
        f"Привет, {html.bold(html.quote(message.from_user.full_name))}!"
        f"\nДанный бот тренирует навыки решения задач по программированию."
        f"\nКаждый день — новая задача. За правильные ответы начисляются очки."
        f"\nСегодня у вас {today_total} очков!"
        f"\nЕсли застряли — есть подсказка."
        f"\nДля начала используй /help",
        parse_mode=ParseMode.HTML,
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer("Выберите язык:", reply_markup=get_language_keyboard())

@dp.message(F.text.in_({"Python", "JavaScript"}))
async def select_language(message: Message, state: FSMContext):
    lang = message.text.lower()
    await state.update_data(language=lang)
    await message.answer(
        f"Вы выбрали {message.text}.", reply_markup=get_action_keyboard()
    )

@dp.message(F.text == "К выбору языка")
async def back_to_language(message: Message):
    await message.answer("Выберите язык:", reply_markup=get_language_keyboard())

@dp.message(F.text.lower() == "получить вопрос")
async def send_random_task(message: Message, state: FSMContext):
    user_data = await state.get_data()
    language = user_data.get("language")

    if not language:
        await message.answer("Сначала выберите язык через /help")
        return

    # Используем тот же файл БД
    record = get_random_task(str(DB_PATH), language)
    if not record:
        await message.answer("Вопросов для этого языка пока нет.")
        return

    task_id, question, hint = record

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ввести ответ✅", callback_data=f"get_answer:{task_id}"
                ),
                InlineKeyboardButton(
                    text="Подсказка❓", callback_data=f"get_hint:{task_id}"
                ),
            ]
        ]
    )
    await message.answer(f"Вопрос дня:\n{question}", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("get_hint"))
async def send_hint(callback: CallbackQuery):
    task_id = callback.data.split(":")[1]

    con = db()
    cur = con.cursor()
    cur.execute("SELECT hint FROM tasks WHERE id = ?", (task_id,))
    result = cur.fetchone()
    con.close()

    if result and result[0]:
        await callback.message.answer(f"Подсказка: {result[0]}")
    else:
        await callback.message.answer("Подсказки для этой задачи нет.")
    await callback.answer()

@dp.callback_query(F.data.startswith("get_answer"))
async def ask_fro_answer(callback: CallbackQuery, state: FSMContext):
    task_id = callback.data.split(":")[1]
    await state.update_data(task_id=task_id)
    await callback.message.answer("Введите ваш ответ")
    await state.set_state(AnswerState.waiting_for_answer)
    await callback.answer()





@dp.message(AnswerState.waiting_for_answer, F.text.lower() == "узнать свой счет")
async def score_when_waiting(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username)
    today_total = get_today_score(message.from_user.id)
    await message.reply(f"Сегодня у вас {today_total} очков")

@dp.message(AnswerState.waiting_for_answer, F.text.lower() == "получить вопрос")
async def question_when_waiting(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Окей, давайте заново. Выберите действие:", reply_markup=get_action_keyboard())

@dp.message(AnswerState.waiting_for_answer, F.text == "К выбору языка")
async def back_lang_when_waiting(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Выберите язык:", reply_markup=get_language_keyboard())




@dp.message(AnswerState.waiting_for_answer)
async def check_answer(message: Message, state: FSMContext):
    user_data = await state.get_data()
    task_id = user_data.get("task_id")
    user_answer = (message.text or "").strip()

    con = db(); cur = con.cursor()
    cur.execute("SELECT answer FROM tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    con.close()

    correct = bool(row) and (row[0] or "").strip().lower() == user_answer.lower()

    if correct:
        ensure_user(message.from_user.id, message.from_user.username)
        today_total = add_score_today_and_get_total(message.from_user.id, 1)
        await message.answer("✅ Ответ верный! Вам начислен 1 балл.")
        await message.answer(f"Ваш текущий счёт за сегодня: {today_total} очков.")
    else:
        await message.answer("❌ Ответ неверный. Попробуйте ещё.")

    # важно: очищаем состояние всегда
    await state.clear()




@dp.message(F.text.lower() == "узнать свой счет")
async def get_task(message: Message, state: FSMContext):
    await state.clear()
    ensure_user(message.from_user.id, message.from_user.username)
    today_total = get_today_score(message.from_user.id)
    await message.reply(f"Сегодня у вас {today_total} очков")


async def main() -> None:
    ensure_schema()
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # На время диагностики можно включить:
    # print("DB path:", DB_PATH.resolve())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())