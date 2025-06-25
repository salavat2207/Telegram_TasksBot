import random
import sqlite3
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

load_dotenv()

# --- Инициализация базы данных ---
conn = sqlite3.connect("sessions.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        chat_id INTEGER PRIMARY KEY,
        session_id INTEGER,
        players TEXT
    )
""")
cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        session_id INTEGER,
        user_id INTEGER,
        action TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# --- Утилиты ---
def get_active_session(chat_id):
    cur.execute("SELECT session_id FROM sessions WHERE chat_id=?", (chat_id,))
    result = cur.fetchone()
    return result[0] if result else None

def add_player(chat_id, user_id):
    cur.execute("SELECT players FROM sessions WHERE chat_id=?", (chat_id,))
    result = cur.fetchone()
    if not result:
        return False
    players = result[0].split(',') if result[0] else []
    if str(user_id) not in players:
        if len(players) >= 5:
            return False
        players.append(str(user_id))
        cur.execute("UPDATE sessions SET players=? WHERE chat_id=?", (','.join(players), chat_id))
        conn.commit()
    return True

def remove_player(chat_id, user_id):
    cur.execute("SELECT players FROM sessions WHERE chat_id=?", (chat_id,))
    result = cur.fetchone()
    if not result:
        return
    players = result[0].split(',') if result[0] else []
    if str(user_id) in players:
        players.remove(str(user_id))
        cur.execute("UPDATE sessions SET players=? WHERE chat_id=?", (','.join(players), chat_id))
        conn.commit()

def log_action(session_id, user_id, action):
    cur.execute("INSERT INTO logs (session_id, user_id, action) VALUES (?, ?, ?)", (session_id, user_id, action))
    conn.commit()

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я DnD Game Master Bot 🎲\nИспользуй /start_game чтобы начать сессию.")

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session_id = random.randint(1000, 9999)
    cur.execute("INSERT OR REPLACE INTO sessions (chat_id, session_id, players) VALUES (?, ?, ?)", (chat_id, session_id, ""))
    conn.commit()
    await update.message.reply_text(f"🎮 Сессия #{session_id} начата! Игроки могут присоединяться через /join_game")

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    session_id = get_active_session(chat_id)
    if not session_id:
        await update.message.reply_text("Нет активной сессии. Введите /start_game.")
        return
    if not add_player(chat_id, user_id):
        await update.message.reply_text("Невозможно присоединиться (возможно, максимум игроков — 5).")
        return
    await update.message.reply_text(f"Игрок {update.effective_user.first_name} присоединился!")
    log_action(session_id, user_id, "присоединился к игре")

async def create_character(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = { "Сила": random.randint(3,18), "Ловкость": random.randint(3,18), "Интеллект": random.randint(3,18) }
    races = ["Человек", "Эльф", "Орк", "Гном"]
    classes = ["Воин", "Маг", "Разбойник", "Жрец"]
    char = f"🎭 Персонаж:\nРаса: {random.choice(races)}\nКласс: {random.choice(classes)}\n" + "\n".join([f"{k}: {v}" for k,v in stats.items()])
    await update.message.reply_text(char)

async def roll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        expr = context.args[0] if context.args else "1d20"
        count, sides = map(int, expr.lower().split("d"))
        rolls = [random.randint(1, sides) for _ in range(count)]
        await update.message.reply_text(f"🎲 Бросок {expr}: {rolls} = {sum(rolls)}")
    except:
        await update.message.reply_text("Формат: /roll d20 или /roll 2d6")

async def main():
    token = os.getenv("TOKEN")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("start_game", start_game))
    app.add_handler(CommandHandler("join_game", join_game))
    app.add_handler(CommandHandler("create_character", create_character))
    app.add_handler(CommandHandler("roll", roll))

    print("✅ Бот запущен!")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    import nest_asyncio

    nest_asyncio.apply()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())