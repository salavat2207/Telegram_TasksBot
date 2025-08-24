import sqlite3
import random


"""Получить рандомный вопрос из БД"""
def get_random_task(db_path, language):
    import sqlite3, random
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, question, hint FROM tasks WHERE lower(language) = lower(?)",
        (language,)
    )
    rows = cursor.fetchall()
    conn.close()
    return random.choice(rows) if rows else None



"""Получить подсказку с БД"""
def get_hint(db_path, language):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT question FROM tasks WHERE language = ?", (language,))
    rows = [row[5] for row in cursor.fetchall()]
    conn.close()
    return random.choice(rows) if rows else None

"""Ввод и проверка ответа"""
def get_answer(db_path, language):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT question FROM tasks WHERE language = ?", (language,))
    rows = [row[3] for row in cursor.fetchall()]
    conn.close()
    return random.choice(rows) if rows else None


"""Подсчет очков"""
def solved_total(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
