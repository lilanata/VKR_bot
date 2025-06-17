import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from core.db import insert
from core.models.command_config import CommandConfig
from core.models.users import create_user, select_user, exist
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)


def login():
    """
    /login — шифрование пароля и сохранение/обновление пользователя в БД.
    """

    @available_or_message
    @measure_duration("login")
    async def _login(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = CommandConfig.get("login")
        insert("data", {"type": "command", "command": "login", "timestamp": time.time()})

        if len(context.args) != 1:
            await update.message.reply_text(cfg.get_message("incorrect_format"))
            return
        group = context.args[0]

        tg_id = update.effective_user.id
        username = update.effective_user.username or ""

        if exist(tg_id):
            user = select_user(tg_id)
            user.group = group
        else:
            create_user(tg_id, username, group)

        await update.message.reply_text(cfg.get_message("correct_data"))

    return _login
