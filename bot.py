import os
import logging
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from groq import Groq
from supabase import create_client

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

logging.basicConfig(level=logging.INFO)

NICHES = {
    "☕ Кофейня": "Ты — SMM-менеджер уютной кофейни. Стиль: тёплый, живой, как пишет хозяин который любит гостей. Короткие предложения, живые детали, никакого официоза. Без хэштегов.",
    "💇 Салон красоты": "Ты — SMM-менеджер салона красоты. Стиль: экспертный но тёплый. Акцент на трансформации и эмоциях клиента. Не продаёт — вдохновляет.",
    "🏋️ Фитнес": "Ты — SMM-менеджер фитнес-клуба. Стиль: мотивирующий и прямой. Конкретные факты и цифры. Без клише типа 'ты можешь всё!'.",
    "🍕 Ресторан": "Ты — SMM-менеджер ресторана. Стиль: чувственный и вкусный. Акцент на деталях: запах, текстура, вкус. Рассказывай истории через еду.",
    "👗 Бутик": "Ты — SMM-менеджер модного бутика. Стиль: стильный и вдохновляющий. Говори об одежде через уверенность и образ жизни. Не продавай вещи — продавай ощущение.",
}

POST_TYPES = ["💡 Совет", "📖 История клиента", "🎁 Акция"]
WEEK_PLAN = ["Пн: Совет", "Вт: История", "Ср: Акция", "Чт: Совет", "Пт: История", "Сб: Акция", "Вс: Совет"]

ASK_NICHE, ASK_NAME, ASK_TYPE, ASK_DETAIL = range(4)

def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def save_user(user_id, niche, name):
    try:
        db = get_supabase()
        db.table("users").upsert({
            "user_id": user_id,
            "niche": niche,
            "name": name
        }).execute()
    except Exception as e:
        print(f"DB error: {e}")

def get_user(user_id):
    try:
        db = get_supabase()
        result = db.table("users").select("*").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        print(f"DB error: {e}")
    return None

def type_keyboard():
    return ReplyKeyboardMarkup(
        [[t] for t in POST_TYPES] + [["📅 План на неделю"]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user:
        context.user_data["niche"] = user["niche"]
        context.user_data["name"] = user["name"]
        await update.message.reply_text(
            f"С возвращением! Пишу для {user['niche']} «{user['name']}» 🚀\n\nЧто нужно?",
            reply_markup=type_keyboard()
        )
        return ASK_TYPE

    keyboard = [[n] for n in NICHES.keys()]
    await update.message.reply_text(
        "Привет! Я PostPilot — пишу посты для твоего бизнеса 🚀\n\nКакой у тебя бизнес?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_NICHE

async def ask_niche(update: Update, context: ContextTypes.DEFAULT_TYPE):
    niche = update.message.text
    if niche not in NICHES:
        keyboard = [[n] for n in NICHES.keys()]
        await update.message.reply_text(
            "Выбери нишу из списка 👇",
            reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ASK_NICHE
    context.user_data["niche"] = niche
    await update.message.reply_text(
        f"Отлично, {niche}! Как называется твой бизнес?",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text
    await update.message.reply_text(
        "Что нужно?",
        reply_markup=type_keyboard()
    )
    return ASK_TYPE

async def generate_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    niche = context.user_data.get("niche", "")
    name = context.user_data.get("name", "")
    user_id = update.effective_user.id

    save_user(user_id, niche, name)
    await update.message.reply_text("Составляю план на неделю... 📅 Это займёт около минуты.")

    system_prompt = NICHES.get(niche, "Ты — SMM-менеджер.")
    days = [
        ("Понедельник", "полезный совет"),
        ("Вторник", "история клиента"),
        ("Среда", "акция или спецпредложение"),
        ("Четверг", "полезный совет"),
        ("Пятница", "история клиента"),
        ("Суббота", "акция или спецпредложение"),
        ("Воскресенье", "тёплый пост про команду или ценности"),
    ]

    try:
        client = Groq(api_key=GROQ_KEY)
        week_text = f"📅 *План постов на неделю для «{name}»*\n\n"

        for day, post_type in days:
            prompt = f"""Напиши короткий пост для бизнеса "{name}" на {day}.
Тип: {post_type}.
Формат: только текст поста, 2-3 предложения. Без заголовков и пояснений."""

            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200
            )
            post = response.choices[0].message.content.strip()
            week_text += f"*{day}* ({post_type})\n{post}\n\n"

        await update.message.reply_text(
            week_text,
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            "Готово! Копируй и публикуй 🎉\n\nЧто ещё?",
            reply_markup=type_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка: {e}",
            reply_markup=type_keyboard()
        )

    return ASK_TYPE

async def ask_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    post_type = update.message.text

    if post_type == "📅 План на неделю":
        return await generate_week(update, context)

    if post_type not in POST_TYPES:
        await update.message.reply_text(
            "Выбери из списка 👇",
            reply_markup=type_keyboard()
        )
        return ASK_TYPE

    context.user_data["post_type"] = post_type
    await update.message.reply_text(
        "Есть конкретная деталь или повод?\n(или напиши 'нет' — придумаю сам)",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_DETAIL

async def generate_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    detail = update.message.text
    niche = context.user_data.get("niche", "")
    name = context.user_data.get("name", "")
    post_type = context.user_data.get("post_type", "")
    user_id = update.effective_user.id

    save_user(user_id, niche, name)
    await update.message.reply_text("Пишу пост... ✍️")

    system_prompt = NICHES.get(niche, "Ты — SMM-менеджер.")
    user_prompt = f"""Напиши пост для бизнеса "{name}".
Тип поста: {post_type}
{"Деталь/повод: " + detail if detail.lower() != "нет" else "Придумай подходящую тему сам."}

Формат ответа:
ТЕКСТ ПОСТА:
[3-5 предложений]

ИДЕЯ ДЛЯ ФОТО:
[одна строка]

ЛУЧШЕЕ ВРЕМЯ:
[утро/день/вечер]"""

    try:
        client = Groq(api_key=GROQ_KEY)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=500
        )
        post = response.choices[0].message.content
        await update.message.reply_text(post)
        await update.message.reply_text(
            "Что дальше?",
            reply_markup=type_keyboard()
        )
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка: {e}",
            reply_markup=type_keyboard()
        )

    return ASK_TYPE

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_NICHE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_niche)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_type)],
            ASK_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_post)],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(conv)
    print("PostPilot запущен! ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
