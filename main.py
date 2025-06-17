from datetime import timedelta
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from flask import Flask, redirect

load_dotenv()
import asyncio
from threading import Thread

import logging
import os
import sys

import colorlog
from telegram import ReplyKeyboardMarkup, BotCommand
from telegram.ext import ApplicationBuilder, Application

from bot import register_handlers
from scheduler import background_check
from utils.logger_utils import SafeColorHandler, CustomLogMiddleware
from webapp.routes import register_blueprints

LOG_FORMAT = "[{asctime}] {log_color}{name:^24} | {levelname:^8} | {message}"
DATE_FORMAT = "%d.%m.%Y %H:%M:%S"
LOG_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

formatter = colorlog.ColoredFormatter(
    fmt=LOG_FORMAT,
    datefmt=DATE_FORMAT,
    log_colors=LOG_COLORS,
    reset=False,
    style='{'
)

handler = SafeColorHandler(stream=sys.stdout)
handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)

log_path = os.path.join("logs", "app.log")
log_dir = os.path.dirname(log_path)
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)

file_handler = RotatingFileHandler(
    log_path,
    maxBytes=50 * 1024 * 1024,
    backupCount=1024,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
root_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)


def create_flask_app(bot) -> Flask:
    base = os.path.dirname(__file__)
    app = Flask(
        __name__,
        template_folder=os.path.join(base, "webapp", "templates"),
        static_folder=os.path.join(base, "webapp", "static")
    )
    app.tg_app = bot
    app.bot = bot.bot
    app.config["BOT"] = bot.bot
    app.wsgi_app = CustomLogMiddleware(app.wsgi_app)
    app.config["SESSION_PERMANENT"] = True
    app.secret_key = os.getenv("ENCRYPTION_KEY")
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=1)
    register_blueprints(app)

    @app.errorhandler(404)
    def page_not_found(e):
        return redirect('/')

    return app


def run_webadmin(bot):
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app = create_flask_app(bot)
    app.run(host='0.0.0.0', port=5000, debug=False)


def main():
    # 1. Настраиваем и запускаем Telegram‑бота
    keyboard = ReplyKeyboardMarkup(
        [["/login", "/get_timetable", "/contacts", "/materials", "/questions", "/create_notification",
          "/notification_list", "/map", "/tracker"]],
        resize_keyboard=True
    )

    async def post_init(application: Application):
        await application.bot.set_my_commands([
            BotCommand("login", "Авторизация /login"),
            BotCommand("contacts", "Получить список контактов института"),
            BotCommand("get_timetable", "Получить расписание"),
            BotCommand("materials", "Посмотреть список своих материалов"),
            BotCommand("questions", "Задать вопрос преподавателю"),
            BotCommand("create_notification", "Создать напоминание"),
            BotCommand("notification_list", "Список ваших напоминаний"),
            BotCommand("map", "Отправить план территории ВУЗа"),
            BotCommand("tracker", "Список Ваших вопросов")
        ])

        asyncio.create_task(background_check(application))

    app = (
        ApplicationBuilder()
        .token(os.environ["TELEGRAM_TOKEN"])
        .post_init(post_init)
        .build()
    )

    register_handlers(app, keyboard)

    Thread(target=run_webadmin, args=(app,), daemon=True).start()

    app.run_polling()


if __name__ == "__main__":
    main()
