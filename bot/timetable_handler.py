import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from core.db import insert
from core.models.command_config import CommandConfig
from core.models.users import select_user
from services.schedule_parser import start_parse  # Импорт новой функции
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)


def get_timetable(encryptor):
    """
    /get_timetable — парсинг расписания пользователя, группировка по дате/времени.
    """

    @available_or_message
    @measure_duration("get_timetable")
    async def _get_timetable(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = CommandConfig.get("get_timetable")
        tg_id = update.effective_user.id
        user = select_user(tg_id)
        if not user or not user.group:
            await update.message.reply_text(cfg.get_message("not_authorized"))
            return

        insert("data", {"type": "command", "command": "get_timetable", "timestamp": time.time()})
        status_msg = await update.message.reply_text(cfg.get_message("get_timetable_data"))

        try:
            # запускаем поиск двух файлов (первый и другой семестр)
            sem1_path, sem2_path = start_parse(user.group)
        except ValueError as e:
            # если не нашли ни одного файла
            await status_msg.edit_text(cfg.get_message("error_collecting_data"))
            return
        except Exception as ex:
            # на всякий случай обрабатываем непредвиденные ошибки
            logger.exception("Ошибка при вызове start_parse")
            await status_msg.edit_text(cfg.get_message("error_collecting_data"))
            return

        # отправляем «первый семестр» (осенне-зимний)
        if sem1_path is not None and sem1_path.exists():
            try:
                with open(sem1_path, "rb") as f1:
                    await update.message.reply_document(
                        document=f1,
                        filename="Осенне-зимний_семестр.xls",
                        caption="Расписание для осенне-зимнего семестра:"
                    )

            except Exception:
                logger.exception(f"Не удалось отправить файл {sem1_path}")
                await update.message.reply_text(cfg.get_message("error_collecting_data"))
        else:
            pass

            # отправляем «другой семестр» (весенне-летний)
        if sem2_path is not None and sem2_path.exists():
            try:
                with open(sem2_path, "rb") as f2:
                    await update.message.reply_document(
                        document=f2,
                        filename="Весенне-летний_семестр.xls",
                        caption="Расписание для весенне-летнего семестра:"
                    )

            except Exception:
                logger.exception(f"Не удалось отправить файл {sem2_path}")
                await update.message.reply_text(cfg.get_message("error_collecting_data"))
        else:
            pass

        await status_msg.delete()

    return _get_timetable
