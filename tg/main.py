from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import aiohttp
import os
from dotenv import load_dotenv
from db.database import SessionLocal
from db.models import User

# === Загрузка переменных окружения ===
load_dotenv()
BOT_TOKEN = os.getenv("TG_API_TOKEN")
MAIN_URL = os.getenv("MAIN_URL")

# === Инициализация FastAPI и Telegram Application ===
app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Временное хранилище сессий: tg_id → {photo_path, matched_id, user_id}
tg_sessions = {}

# === Обработчики ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        token = context.args[0]
        session = SessionLocal()
        user = session.query(User).filter(User.telegram_link_token == token).first()
        if user:
            user.telegram_id = update.effective_user.id
            user.telegram_link_token = None
            session.commit()
            await update.message.reply_text("✅ Telegram успешно привязан.")
        else:
            await update.message.reply_text("⛔ Ссылка недействительна.")
        session.close()
    else:
        await update.message.reply_text("Привет! Отправь фото или выбери действие:", reply_markup=menu_keyboard)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        await update.message.reply_text("Пожалуйста, сначала привяжите Telegram через сайт.")
        session.close()
        return

    # 1. Сообщение «Ожидайте...»
    await update.message.reply_text("⏳ Обработка изображения, пожалуйста, подождите...")

    # 2. Скачивание изображения
    file = await context.bot.get_file(update.message.photo[-1].file_id)
    os.makedirs("tg_uploads", exist_ok=True)
    local_path = f"tg_uploads/{file.file_unique_id}.jpg"
    await file.download_to_drive(local_path)

    # 3. Отправка запроса к FastAPI
    async with aiohttp.ClientSession() as sess:
        with open(local_path, "rb") as f:
            data = aiohttp.FormData()
            data.add_field("file", f, filename="photo.jpg", content_type="image/jpeg")
            data.add_field("user_id", str(user.id))

            async with sess.post(f"{MAIN_URL}/tg_recognize", data=data) as resp:
                result = await resp.json()
    user.face_searches += 1
    session.close()

    if not result.get("matched"):
        await update.message.reply_text("❌ Совпадений не найдено.")
        return

    match = result["matched"]
    tg_sessions[tg_id] = {
        "photo_path": result["input_photo"],
        "matched_id": match["id"],
        "user_id": user.id,
    }

    # 4. Отправка результата с кнопками
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, это он(а)", callback_data="yes"),
            InlineKeyboardButton("❌ Нет, не он(а)", callback_data="no"),
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    with open(os.path.join("known_faces", os.path.basename(match["photo_url"])), "rb") as photo:
        await context.bot.send_photo(
            chat_id=tg_id,
            photo=photo,
            caption=f"Возможно, это {match['name']} ({match['similarity']}%)",
            reply_markup=markup,
        )


async def decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tg_id = update.effective_user.id
    data = tg_sessions.get(tg_id)
    if not data:
        await query.edit_message_text("⛔ Данные устарели. Отправьте фото заново.")
        return

    # Обновление статистики в БД
    session = SessionLocal()
    user = session.query(User).filter(User.id == data["user_id"]).first()
    if not user:
        await query.edit_message_text("⛔ Пользователь не найден, пожалуйста, авторизуйтесь и повторите попытку.")
        session.close()
        return

    if not update.message.photo:
        await update.message.reply_text("⛔ Пожалуйста, отправьте изображение (не видео).")
        session.close()
        return
    
    if query.data == "yes":
        user.confirmed_matches += 1
    elif query.data == "no":
        user.rejected_matches += 1
    session.commit()

    # Отправка решения на сервер (если нужно)
    async with aiohttp.ClientSession() as sess:
        payload = {
            "user_id": str(data["user_id"]),
            "input_path": data["photo_path"],
            "matched_id": str(data["matched_id"]),
            "decision": query.data,
        }
        await sess.post(f"{MAIN_URL}/recognize_decision", data=payload)

    await query.edit_message_caption(
            caption=query.message.caption + "\n\n✅ Ваш ответ учтён.",
            reply_markup=None
        )
    
    tg_sessions.pop(tg_id, None)
    session.close()

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter(User.telegram_id == tg_id).first()

    if not user:
        await update.message.reply_text("⛔ Вы не авторизованы. Привяжите Telegram через сайт.")
        session.close()
        return

    text = (
        f"👤 <b>Профиль</b>\n"
        f"🔗 VisualFacePro: {MAIN_URL}\n"
        f"👨‍💼 Имя: {user.first_name} {user.last_name}\n"
        f"📧 Email: {user.email}\n"
        f"🛡️ Роль: {user.role}\n"
        f"🗓️ Дата создания: {str(user.created_at).split('.')[0][:16]}\n"
        f"🆔 Ваш ID: {user.telegram_id}\n"
        f"\n📊 Статистика:\n\n"
        f"  ✅ Подтверждено: {user.confirmed_matches}\n"
        f"  ❌ Отклонено: {user.rejected_matches}\n"
        f"  🔍 Всего поисков: {user.face_searches}"
    )

    await update.message.reply_text(text, parse_mode="HTML")
    session.close()

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "ℹ️ Телеграмм бот — VisualFacePro\n"
        "Система определения лиц на изображениях (в будущем — и видео) на основе векторов лица.\n\n"
        "Преимущества:\n"
        "• Точное определение за счёт уникальности каждого лица\n"
        "• Большая база данных\n"
        "• Возможность обратной связи\n\n"
        "Создано:\n"
        f"• Бот дополнение к сайту: {MAIN_URL}\n"
        "• Только для образовательных целей\n\т"
        "Создано в рамках прохождения ознакомительной практики:\n"
        "• Студент: ДГТУ\n"
        "• Факультет: ИиВТ\n"
        "• Группа: ВИ13\n"
        "• ФИО: Карпов Степан Викторович\n\n"
        "По всем вопросам касательно сервиса обращаться напрямую @Karpov_Stepan\n"
        "⚠️ Сервис не несёт ответственности за вашу реализацию."
    )
    await update.message.reply_text(msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📷 Поиск":
        await update.message.reply_text("Отправьте фотографию лица для поиска.")
    elif text == "👤 Профиль":
        await show_profile(update, context)
    elif text == "ℹ️ Информация":
        await show_info(update, context)

async def quit_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    session = SessionLocal()
    user = session.query(User).filter(User.telegram_id == tg_id).first()
    if not user:
        await update.message.reply_text("Вы не авторизованы.")
        session.close()
        return

    await update.message.reply_text("❌ Активная сессия завершена. Рекомендуем сменить пароль.")
    session.close()


# === Привязка обработчиков ===
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
telegram_app.add_handler(CallbackQueryHandler(decision_callback))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_handler(CommandHandler("profile", show_profile))
telegram_app.add_handler(CommandHandler("info", show_info))
telegram_app.add_handler(CommandHandler("quit", quit_session))

menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[["📷 Поиск", "👤 Профиль", "ℹ️ Информация"]],
    resize_keyboard=True,
)

# === Запуск бота при старте FastAPI ===
@app.on_event("startup")
async def startup_event():
    import asyncio
    asyncio.create_task(telegram_app.run_polling(close_loop=False))
