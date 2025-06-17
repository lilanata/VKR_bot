import os

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler


# Команда /map – отправляет схему ВУЗа из data/scheme.jpg
async def map_vuza(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    script_dir = os.path.dirname(__file__)
    img_path = os.path.join(script_dir, os.pardir, "data", "scheme.jpg")
    try:
        with open(img_path, "rb") as f:
            await update.message.reply_photo(photo=f)
    except FileNotFoundError:
        await update.message.reply_text("Изображение 'scheme.jpg' не найдено.")


def get_map_handler() -> CommandHandler:
    return CommandHandler("map", map_vuza)
