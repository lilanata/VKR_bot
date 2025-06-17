import logging
import os
import time
from pathlib import Path
from urllib.parse import quote

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
)

from core.db import insert
from core.models.command_config import CommandConfig
from core.models.users import select_user
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)

# Базовая папка, где лежат материалы (от корня проекта)
BASE_MATERIALS_DIR = Path(__file__).parent.parent / "materials"


# Например, если структура такая:
# └── project_root/
#     ├── bot/
#     │   └── materials_handler.py
#     ├── materials/
#     │   └── 23ВВВ2/
#     │       ├── file1.pdf
#     │       └── file2.zip
#     └── ...

# Функция-генератор хэндлера для команды /materials
def materials():
    """
    /materials — Доступ к материалам: бот читает файлы из папки materials/<группа>/
    и выводит список в виде InlineKeyboard. При нажатии на кнопку
    бот отправит соответствующий файл.
    """

    @available_or_message
    @measure_duration("materials")
    async def _materials(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_telegram_id = update.effective_user.id
        user = select_user(user_telegram_id)
        cfg = CommandConfig.get("materials")

        # Проверяем, что пользователь авторизован и у него есть группа
        if not user or not user.group:
            msg = cfg.get_message(
                "no_group",
                default="Вы не указали группу. Напишите боту /start и заполните данные."
            )
            await update.message.reply_text(msg)
            return

        insert("data", {
            "type": "command",
            "command": "materials",
            "timestamp": time.time()
        })

        # Папка конкретной группы
        group_name = user.group.strip().upper()
        group_dir = BASE_MATERIALS_DIR / group_name

        # Создаём папку, если её вообще нет (чтобы преподаватель мог туда загружать вручную):
        # (но раз она ещё не существовала, значит файлов там точно нет)
        if not group_dir.exists():
            try:
                group_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Не удалось создать директорию для материалов: {group_dir} — {e}")

        # Формируем «статусное» сообщение, пока ищем файлы
        status_msg = await update.message.reply_text(
            cfg.get_message("materials_data", default="Ищем материалы для вашей группы…")
        )

        # Список всех файлов (только обычные файлы, без папок) в group_dir
        files = []
        if group_dir.exists() and group_dir.is_dir():
            # Оставляем только файлы (не папки), без скрытых
            for entry in sorted(group_dir.iterdir()):
                if entry.is_file() and not entry.name.startswith("."):
                    files.append(entry.name)

        # Если файлов нет
        if not files:
            await status_msg.edit_text(
                cfg.get_message(
                    "no_materials",
                    default="Преподаватель для вашей группы ничего не загрузил."
                )
            )
            return

        # Иначе: формируем Inline-кнопки по каждому файлу
        keyboard = []
        for filename in files:
            # Здесь encode необходим, чтобы в callback_data не было пробелов и специальных символов
            callback_data = f"material:{quote(group_name)}:{quote(filename)}"
            keyboard.append([InlineKeyboardButton(text=filename, callback_data=callback_data)])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Отправляем сообщение с кнопками
        await status_msg.edit_text(
            cfg.get_message(
                "materials_list",
                default="Список материалов для вашей группы. Нажмите на название, чтобы получить файл:"
            ),
            reply_markup=reply_markup
        )

    return CommandHandler("materials", _materials)


# Хэндлер для CallbackQuery: при выборе конкретного файла
async def materials_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Получаем callback_data вида "material:<группа>:<имя_файла>"
    Читаем файл из папки materials/<группа>/<имя_файла> и отправляем его пользователю.
    """
    query = update.callback_query
    await query.answer()  # сразу отвечаем на callback, чтобы убрать «часики»

    cfg = CommandConfig.get("materials")
    data = query.data  # формата "material:<group>:<filename>"

    try:
        _, raw_group, raw_filename = data.split(":", maxsplit=2)
        # URL-декодируем (на случай спецсимволов)
        group_name = Path(os.path.normpath(raw_group))
        filename = Path(os.path.normpath(raw_filename))

        # Полный путь к файлу
        file_path = BASE_MATERIALS_DIR / group_name / filename

        # Дополнительная защита: не позволяем выйти за пределы BASE_MATERIALS_DIR
        try:
            file_path = file_path.resolve(strict=True)
            if BASE_MATERIALS_DIR.resolve() not in file_path.parents and BASE_MATERIALS_DIR.resolve() != file_path.parent:
                raise Exception("Попытка доступа к файлу вне папки materials")
        except FileNotFoundError:
            raise

        if not file_path.exists() or not file_path.is_file():
            await query.edit_message_text(
                cfg.get_message("file_not_found", default="Файл не найден. Возможно, он был удалён.")
            )
            return

        # Отправляем файл как документ
        # Если файл слишком большой, он может не отправиться – следите, чтобы размер не превышал лимиты Telegram (~50 МБ).
        try:
            with open(file_path, "rb") as f:
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=f,
                    filename=filename.name
                )
        except Exception as send_exc:
            logger.exception(f"Ошибка при отправке файла {file_path}: {send_exc}")
            await query.edit_message_text(
                cfg.get_message("error_sending_file", default="Не удалось отправить файл. Попробуйте позже.")
            )
    except Exception as ex:
        logger.exception(f"Ошибка в materials_callback: {ex}")
        await query.edit_message_text(
            cfg.get_message("error_collecting_data", default="Произошла ошибка при обработке вашего запроса.")
        )
