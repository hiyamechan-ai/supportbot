import random
import logging
from time import time

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import aiosqlite

from config import GROUP_ID, ADMIN_IDS
from database import get_active_tickets, get_ticket, add_ticket, update_last_activity, close_ticket

router = Router()

# Антиспам
antispam = {}

async def check_antispam(user_id: int) -> bool:
    global antispam
    now = time()
    times = [t for t in antispam.get(user_id, []) if now - t < 30]
    if len(times) >= 10:
        return False
    times.append(now)
    antispam[user_id] = times
    return True

async def create_new_ticket(source, type_: str, bot: Bot):
    is_callback = isinstance(source, CallbackQuery)
    user = source.from_user if is_callback else source.from_user
    answer = source.message.answer if is_callback else source.answer
    user_id = user.id
    username = user.username or "no_username"

    if await get_ticket(user_id):
        await answer("У вас уже есть открытый тикет, чтобы начать новый закройте его. /cancel.")
        if is_callback:
            await source.answer()
        return

    if type_ == "ticket":
        topic_name = str(random.randint(100000, 999999))
        db_username = None
        intro = "Новый тикет, жалоба анонимна"
    else:
        topic_name = f"{username}_{type_}_{random.randint(1000, 9999)}"
        db_username = username
        intro_text = {"help": "вопрос", "appeal": "апелляция"}.get(type_, type_)
        intro = f"Новый тикет от @{username} ({intro_text})"

    try:
        topic = await bot.create_forum_topic(GROUP_ID, topic_name)
        topic_id = topic.message_thread_id
    except Exception as e:
        logging.error(f"Ошибка создания топика: {e}")
        await answer("Не удалось создать тикет. Попробуйте позже.")
        return

    await add_ticket(user_id, db_username, type_, topic_id, topic_name)
    await bot.send_message(GROUP_ID, intro, message_thread_id=topic_id)
    await answer("Опишите вашу проблему или вопрос, наш модератор посторается помочь вам в ближайшее время. Чтобы закрыть тикет, используйте команду /cancel.")
    if is_callback:
        await source.answer()

@router.message(Command("start"))
async def cmd_start(message: Message):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подать жалобу (анонимно)", callback_data="type_ticket")],
        [InlineKeyboardButton(text="Задать вопрос", callback_data="type_help")],
        [InlineKeyboardButton(text="Подать апелляцию", callback_data="type_appeal")],
    ])
    if await get_ticket(message.from_user.id):
        await message.answer("У вас уже есть открытый тикет, чтобы начать новый закройте его. /cancel.")
    else:
        await message.answer("Привет. Что ты хотел?", reply_markup=markup)

@router.callback_query(F.data.startswith("type_"))
async def callback_type(callback: CallbackQuery, bot: Bot):
    type_ = callback.data.split("_")[1]
    await create_new_ticket(callback, type_, bot)

@router.message(Command("ticket", "help", "appeal"))
async def cmd_direct(message: Message, bot: Bot):
    cmd = message.text[1:]  # ticket, help или appeal
    await create_new_ticket(message, cmd, bot)

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, bot: Bot):
    user_id = message.from_user.id
    if await get_ticket(user_id):
        await close_ticket(user_id, bot, GROUP_ID, "^_~")
        await message.answer("Тикет закрыт.")
    else:
        await message.answer("У вас нет активного тикета.")

@router.message(F.chat.type == "private")
async def private_forward(message: Message, bot: Bot):
    user_id = message.from_user.id
    ticket = await get_ticket(user_id)
    if not ticket:
        await message.answer("Нет активного тикета. Нажмите /start чтобы посмотреть варианты запросов.")
        return

    if not await check_antispam(user_id):
        await message.answer("Слишком много сообщений. Подождите 30 секунд.")
        return

    await update_last_activity(user_id)
    topic_id = ticket[3]
    is_anon = ticket[2] == "ticket"

    if is_anon:
        if message.text:
            await bot.send_message(GROUP_ID, f" {message.text}", message_thread_id=topic_id)
        elif message.photo:
            await bot.send_photo(GROUP_ID, message.photo[-1].file_id, caption=f"Пользователь отправил фото", message_thread_id=topic_id)
        elif message.video:
            await bot.send_video(GROUP_ID, message.video.file_id, caption=f"Пользователь отправил видео", message_thread_id=topic_id)
        elif message.document:
            await bot.send_document(GROUP_ID, message.document.file_id, caption=f"Пользователь отправил файл", message_thread_id=topic_id)
        elif message.voice:
            await bot.send_voice(GROUP_ID, message.voice.file_id, caption=f"Пользователь отправил голосовое", message_thread_id=topic_id)
        elif message.sticker:
            await bot.send_sticker(GROUP_ID, message.sticker.file_id, message_thread_id=topic_id)
        elif message.animation:
            await bot.send_animation(GROUP_ID, message.animation.file_id, caption=f"Пользователь отправил GIF", message_thread_id=topic_id)
        else:
            await bot.send_message(GROUP_ID, f"Пользователь отправил неподдерживаемый тип сообщения.", message_thread_id=topic_id)
    else:
        await message.copy_to(GROUP_ID, message_thread_id=topic_id)

@router.message(Command("db_tickets"))
async def cmd_db_tickets(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
        
    tickets = await get_active_tickets()
    if not tickets:
        await message.answer("Активных тикетов нет.")
        return
        
    text = "Активные тикеты:\n\n"
    for t in tickets:
        user_id, username, type_, start_time, topic_name = t
        ticket = await get_ticket(user_id)
        last_act = ticket[6] if ticket else "—"
        user_str = "Аноним" if username is None else f"@{username}"
        text += f"{user_str} | {type_} | last: {last_act} | старт: {start_time}\n"
    
    await message.answer(text or "Нет активных тикетов")

@router.message(F.chat.id == GROUP_ID, F.message_thread_id)
async def group_forward(message: Message, bot: Bot):
    if message.from_user.is_bot:
        return

    topic_id = message.message_thread_id
    async with aiosqlite.connect("tickets.db") as db:
        async with db.execute("SELECT user_id FROM tickets WHERE topic_id = ? AND active = 1", (topic_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                await message.copy_to(row[0])

@router.message(Command("list_tickets"))
async def cmd_list(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    tickets = await get_active_tickets()
    if not tickets:
        await message.answer("Нет активных тикетов.")
        return
    text = "Активные тикеты:\n\n"
    for t in tickets:
        user_str = "Пользователь" if t[1] is None else f"@{t[1]}"
        text += f"{user_str} | {t[2]} | {t[3]} | топик: {t[4]}\n"
    await message.answer(text)