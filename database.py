import aiosqlite

DB_FILE = "tickets.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                type TEXT,
                topic_id INTEGER,
                topic_name TEXT,
                start_time TEXT,
                last_activity TEXT,
                active INTEGER
            )
        """)
        await db.commit()

async def add_ticket(user_id: int, username: str | None, type_: str, topic_id: int, topic_name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            REPLACE INTO tickets 
            (user_id, username, type, topic_id, topic_name, start_time, last_activity, active)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'), 1)
        """, (user_id, username, type_, topic_id, topic_name))
        await db.commit()

async def get_ticket(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT * FROM tickets WHERE user_id = ? AND active = 1", (user_id,)) as cursor:
            return await cursor.fetchone()

async def update_last_activity(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE tickets SET last_activity = datetime('now') WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_active_tickets():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id, username, type, start_time, topic_name FROM tickets WHERE active = 1") as cursor:
            return await cursor.fetchall()

async def close_ticket(user_id: int, bot, group_id: int, reason: str = "вручную"):
    ticket = await get_ticket(user_id)
    if not ticket:
        return

    topic_id = ticket[3]
    try:
        await bot.close_forum_topic(chat_id=group_id, message_thread_id=topic_id)
        await bot.send_message(group_id, f"Тикет закрыт: {reason}.", message_thread_id=topic_id)
    except Exception as e:
        print(f"Ошибка закрытия топика: {e}")

    await bot.send_message(user_id, f"Ваш тикет закрыт ({reason}).")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE tickets SET active = 0 WHERE user_id = ?", (user_id,))
        await db.commit()