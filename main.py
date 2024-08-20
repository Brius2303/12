import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

API_TOKEN = '7263590944:AAGLVSZixmLnwy9UAIp33SJw1-xX927Tabo'

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

def initialize_database():
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        current_state TEXT
    );
    CREATE TABLE IF NOT EXISTS notes (
        user_id INTEGER,
        note TEXT,
        note_id INTEGER PRIMARY KEY AUTOINCREMENT
    );
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.")

def renumber_notes(chat_id):
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()

    # Получаем все заметки для данного пользователя, отсортированные по текущему note_id
    cursor.execute("SELECT note_id FROM notes WHERE user_id = ? ORDER BY note_id", (chat_id,))
    notes = cursor.fetchall()

    # Присваиваем новые идентификаторы
    new_id = 1
    for (old_id,) in notes:
        cursor.execute("UPDATE notes SET note_id = ? WHERE user_id = ? AND note_id = ?", (new_id, chat_id, old_id))
        new_id += 1

    conn.commit()
    conn.close()

    print("Notes renumbered.")

async def handle_message(message: types.Message):
    chat_id = message.chat.id
    text = message.text

    if text == '/start':
        await bot.send_message(chat_id, "Добро пожаловать! Выберите действие:")
        await show_main_menu(chat_id)
        return

    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT current_state FROM users WHERE user_id = ?", (chat_id,))
    state = cursor.fetchone()
    state = state[0] if state else None

    print(f"User state for chatId {chat_id}: {state}")  # Debug log

    if state is None:
        await bot.send_message(chat_id, "Пожалуйста, выберите действие через меню.")
        return

    await handle_user_message(chat_id, text, conn, cursor)
    conn.close()

async def handle_user_message(chat_id, text, conn, cursor):
    cursor.execute("SELECT current_state FROM users WHERE user_id = ?", (chat_id,))
    state = cursor.fetchone()
    state = state[0] if state else None

    print(f"Handling message in state: {state}")  # Debug log

    if state is None:
        await bot.send_message(chat_id, "Пожалуйста, выберите действие через меню.")
        return

    if state == "adding_note":
        cursor.execute("INSERT INTO notes (user_id, note) VALUES (?, ?)", (chat_id, text))
        conn.commit()
        renumber_notes(chat_id)  # Перенумерация после добавления
        await bot.send_message(chat_id, "Заметка добавлена.")
        await show_main_menu(chat_id)
        await update_user_state(chat_id, None, conn, cursor)

    elif state == "deleting_note":
        if text.isdigit():
            note_id = int(text)
            cursor.execute("DELETE FROM notes WHERE user_id = ? AND note_id = ?", (chat_id, note_id))
            conn.commit()
            renumber_notes(chat_id)  # Перенумерация после удаления
            await bot.send_message(chat_id, "Заметка удалена.")
            await show_main_menu(chat_id)
        else:
            await bot.send_message(chat_id, "Укажите корректный ID заметки.")
        await update_user_state(chat_id, None, conn, cursor)

    elif state == "editing_note":
        parts = text.split(' ', 1)
        if len(parts) == 2 and parts[0].isdigit():
            note_id_to_edit = int(parts[0])
            new_text = parts[1]
            cursor.execute("UPDATE notes SET note = ? WHERE user_id = ? AND note_id = ?", (new_text, chat_id, note_id_to_edit))
            conn.commit()
            renumber_notes(chat_id)  # Перенумерация после редактирования
            await bot.send_message(chat_id, "Заметка изменена.")
            await show_main_menu(chat_id)
        else:
            await bot.send_message(chat_id, "Отправьте ID заметки и новый текст через пробел.")
        await update_user_state(chat_id, None, conn, cursor)

    else:
        await bot.send_message(chat_id, "Некорректный ввод. Попробуйте еще раз.")

async def handle_callback_query(callback_query: types.CallbackQuery):
    chat_id = callback_query.message.chat.id
    data = callback_query.data

    print(f"Callback query data: {data}")  # Debug log

    if data == "add_note":
        await bot.send_message(chat_id, "Отправь мне текст заметки:")
        await update_user_state(chat_id, "adding_note")
    elif data == "list_notes":
        await list_notes(chat_id)
    elif data == "delete_note":
        await bot.send_message(chat_id, "Отправь мне ID заметки для удаления:")
        await update_user_state(chat_id, "deleting_note")
    elif data == "edit_note":
        await bot.send_message(chat_id, "Отправь мне ID заметки и новый текст через пробел (например, '1 Новая заметка'):")
        await update_user_state(chat_id, "editing_note")

async def show_main_menu(chat_id):
    inline_kb = InlineKeyboardMarkup(row_width=1)
    inline_kb.add(
        InlineKeyboardButton("Добавить заметку", callback_data="add_note"),
        InlineKeyboardButton("Посмотреть заметки", callback_data="list_notes"),
        InlineKeyboardButton("Удалить заметку", callback_data="delete_note"),
        InlineKeyboardButton("Изменить заметку", callback_data="edit_note")
    )
    await bot.send_message(chat_id, "Выберите действие:", reply_markup=inline_kb)

async def list_notes(chat_id):
    conn = sqlite3.connect('notes.db')
    cursor = conn.cursor()
    cursor.execute("SELECT note_id, note FROM notes WHERE user_id = ?", (chat_id,))
    rows = cursor.fetchall()

    if not rows:
        await bot.send_message(chat_id, "У вас нет заметок.")
    else:
        notes_text = "\n".join(f"{row[0]}: {row[1]}" for row in rows)
        await bot.send_message(chat_id, f"Ваши заметки:\n{notes_text}")

    conn.close()

async def update_user_state(chat_id, state, conn=None, cursor=None):
    if conn is None or cursor is None:
        conn = sqlite3.connect('notes.db')
        cursor = conn.cursor()
    if state is None:
        cursor.execute("UPDATE users SET current_state = NULL WHERE user_id = ?", (chat_id,))
    else:
        cursor.execute("REPLACE INTO users (user_id, current_state) VALUES (?, ?)", (chat_id, state))
    conn.commit()

if __name__ == '__main__':
    initialize_database()
    dp.register_message_handler(handle_message, content_types=['text'])
    dp.register_callback_query_handler(handle_callback_query)
    executor.start_polling(dp, skip_updates=True)
