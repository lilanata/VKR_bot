import logging
import os

from telegram import ReplyKeyboardMarkup
from telegram.ext import CommandHandler, CallbackQueryHandler

from services.encryption import EncryptionService
from .contacts_handler import contacts
from .map_handler import get_map_handler
from .materials_handler import materials, materials_callback
from .notifications_handler import notifications
from .questions_handler import questions
from .questions_tracker_handler import get_tracker_handler

from .start_handler import start
from .login_handler import login
from .timetable_handler import get_timetable

logger = logging.getLogger(__name__)


def register_handlers(app, keyboard: ReplyKeyboardMarkup):
    """
    Регистрирует все команды бота.
    """
    encryptor = EncryptionService(os.environ.get("ENCRYPTION_KEY"))

    # Основные команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login(), block=False))
    app.add_handler(CommandHandler("contacts", contacts(), block=False))
    app.add_handler(CommandHandler("get_timetable", get_timetable(encryptor), block=False))
    app.add_handler(materials())
    app.add_handler(CallbackQueryHandler(materials_callback, pattern=r"^material:"))
    app.add_handler(questions())
    conv_notify = notifications()
    app.add_handler(conv_notify)
    app.add_handler(get_map_handler())
    app.add_handler(get_tracker_handler())
