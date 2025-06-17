import logging
import time

from bson import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, \
    filters

from core.models.command_config import CommandConfig
from core.models.notification_config import NotificationConfig
from core.models.users import select_user
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(CREATE_TEXT, CREATE_INTERVAL, LIST_NOTIFY, EDIT_CHOICE, EDIT_TEXT, EDIT_INTERVAL) = range(6)


def _parse_interval_to_seconds(interval_str: str) -> int:
    """
    Преобразует строку "HH:MM:SS" (или "MM:SS"/"SS") в секунды.
    """
    parts = interval_str.strip().split(":")
    if not parts:
        raise ValueError("Пустая строка интервала")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", *parts
    elif len(parts) == 1:
        h, m, s = "0", "0", parts[0]
    else:
        raise ValueError("Неверный формат интервала, ожидать HH:MM:SS")
    try:
        hours, minutes, seconds = int(h), int(m), int(s)
    except ValueError:
        raise ValueError("Часы, минуты и секунды должны быть целыми числами")
    if hours < 0 or minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        raise ValueError("Часы ≥0, минуты/секунды 0–59")
    return hours * 3600 + minutes * 60 + seconds


def notifications():
    """
    Возвращает ConversationHandler и CommandHandler("notification_list", ...).
    Вся логика: / create_notification, / notification_list, выбор напоминания,
    переключение toggle, edit_text, edit_interval, delete, и само редактирование.
    """

    # --- Шаг 1: /create_notification → ввод текста ---
    @available_or_message
    @measure_duration("create_notification_start")
    async def start_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = select_user(update.effective_user.id)
        cfg = CommandConfig.get("notifications")
        if not user:
            await update.message.reply_text(
                cfg.get_message("no_user", default="Вы не зарегистрированы. Сначала /start.")
            )
            return ConversationHandler.END
        # Просим текст напоминания
        await update.message.reply_text(
            cfg.get_message("prompt_text", default="Напишите текст напоминания:"),
            reply_markup=ReplyKeyboardRemove()
        )
        return CREATE_TEXT

    # --- Шаг 2: получен текст, просим интервал ---
    @available_or_message
    @measure_duration("create_notification_text")
    async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        text = update.message.text.strip()
        cfg = CommandConfig.get("notifications")
        if not text:
            await update.message.reply_text(
                cfg.get_message("empty_text", default="Текст не может быть пустым. Попробуйте снова.")
            )
            return CREATE_TEXT
        context.user_data["notif_text"] = text
        await update.message.reply_text(
            cfg.get_message("prompt_interval", default="Введите интервал в формате HH:MM:SS:")
        )
        return CREATE_INTERVAL

    # --- Шаг 3: получен интервал, создаём уведомление и возвращаемся в главное меню ---
    @available_or_message
    @measure_duration("create_notification_interval")
    async def receive_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        interval_str = update.message.text.strip()
        cfg = CommandConfig.get("notifications")
        try:
            interval_seconds = _parse_interval_to_seconds(interval_str)
        except ValueError as e:
            errmsg = f"Неверный формат интервала: {e}. Повторите ввод HH:MM:SS"
            await update.message.reply_text(errmsg)
            return CREATE_INTERVAL

        user_id = update.effective_user.id
        text = context.user_data.get("notif_text", "")
        NotificationConfig.create(user_id=user_id, text=text, interval_seconds=interval_seconds)
        await update.message.reply_text(
            cfg.get_message("created_success", text=text, interval_str=interval_str)
        )
        context.user_data.pop("notif_text", None)
        return ConversationHandler.END

    # --- Шаг 4: /notification_list → показываем список кнопок ---
    @available_or_message
    @measure_duration("notification_list")
    async def notification_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        cfg = CommandConfig.get("notifications")
        user = select_user(user_id)
        if not user:
            await update.message.reply_text(
                cfg.get_message("no_user", default="Вы не зарегистрированы. Сначала /start.")
            )
            return ConversationHandler.END

        notifs = NotificationConfig.get_all_for_user(user_id)
        if not notifs:
            await update.message.reply_text(
                cfg.get_message("no_notifs", default="У вас нет ни одного напоминания.")
            )
            return ConversationHandler.END

        keyboard = []
        for n in notifs:
            preview = n.text if len(n.text) <= 20 else n.text[:17] + "..."
            status = "✅" if n.enabled else "❌"
            btn_text = f"{status} {preview}"
            callback_data = f"notif_select:{str(n.id)}"
            keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])

        await update.message.reply_text(
            cfg.get_message("choose_to_edit", default="Выберите напоминание для редактирования:"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return LIST_NOTIFY

    # --- Шаг 5: пользователь нажал на кнопку напоминания ― показываем детали + кнопки действий ---
    @available_or_message
    @measure_duration("notification_list_callback")
    async def notification_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        cfg = CommandConfig.get("notifications")
        try:
            _, raw_id = query.data.split(":", maxsplit=1)
            notif_id = ObjectId(raw_id)
            notif = NotificationConfig.get(notif_id)

            toggle_text = "Выключить" if notif.enabled else "Включить"
            toggle_cd = f"notif_action:{raw_id}:toggle"
            edit_text_cd = f"notif_action:{raw_id}:edit_text"
            edit_interval_cd = f"notif_action:{raw_id}:edit_interval"
            delete_cd = f"notif_action:{raw_id}:delete"

            buttons = [
                [InlineKeyboardButton(toggle_text, callback_data=toggle_cd)],
                [InlineKeyboardButton("Изменить текст", callback_data=edit_text_cd)],
                [InlineKeyboardButton("Изменить интервал", callback_data=edit_interval_cd)],
                [InlineKeyboardButton("Удалить", callback_data=delete_cd)]
            ]

            details = (
                f"Напоминание:\n"
                f"Текст: {notif.text}\n"
                f"Интервал: {notif.interval // 3600:02d}:"
                f"{(notif.interval % 3600) // 60:02d}:"
                f"{notif.interval % 60:02d}\n"
                f"Включено: {'Да' if notif.enabled else 'Нет'}\n"
                f"Следующий запуск: "
                f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(notif.next_run))}"
            )
            await query.edit_message_text(details, reply_markup=InlineKeyboardMarkup(buttons))
            return EDIT_CHOICE
        except Exception as ex:
            logger.exception(f"Ошибка в notification_list_callback: {ex}")
            await query.edit_message_text(
                cfg.get_message("error_collecting_data", default="Произошла ошибка при выборе напоминания.")
            )
            return ConversationHandler.END

    # --- Шаг 6: обработка действий (toggle / delete / edit_text / edit_interval) ---
    @available_or_message
    @measure_duration("notification_action_callback")
    async def notification_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        cfg = CommandConfig.get("notifications")
        try:
            _, raw_id, action = query.data.split(":", maxsplit=2)
            notif_id = ObjectId(raw_id)
            notif = NotificationConfig.get(notif_id)

            if action == "toggle":
                new_state = not notif.enabled
                NotificationConfig.toggle_enabled(notif_id, new_state)
                await query.edit_message_text(
                    cfg.get_message("toggled", state='включено' if new_state else 'выключено')
                )
                return ConversationHandler.END

            if action == "delete":
                NotificationConfig.delete(notif_id)
                await query.edit_message_text(
                    cfg.get_message("deleted", default="Напоминание удалено.")
                )
                return ConversationHandler.END

            if action == "edit_text":
                context.user_data["edit_id"] = raw_id
                await query.edit_message_text(
                    cfg.get_message("prompt_new_text", default="Введите новый текст напоминания:")
                )
                return EDIT_TEXT

            if action == "edit_interval":
                context.user_data["edit_id"] = raw_id
                await query.edit_message_text(
                    cfg.get_message("prompt_new_interval", default="Введите новый интервал в формате HH:MM:SS:")
                )
                return EDIT_INTERVAL

        except Exception as ex:
            logger.exception(f"Ошибка в notification_action_callback: {ex}")
            await query.edit_message_text(
                cfg.get_message("error_collecting_data", default="Произошла ошибка при обработке действия.")
            )
            return ConversationHandler.END

    # --- Шаг 7: получен новый текст для напоминания (после «Изменить текст») ---
    @available_or_message
    @measure_duration("notification_edit_text")
    async def perform_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        new_text = update.message.text.strip()
        cfg = CommandConfig.get("notifications")
        if not new_text:
            await update.message.reply_text(
                cfg.get_message("empty_text", default="Текст не может быть пустым. Повторите ввод:")
            )
            return EDIT_TEXT

        raw_id = context.user_data.get("edit_id")
        if not raw_id:
            await update.message.reply_text(
                cfg.get_message("error_collecting_data", default="Не удалось найти напоминание.")
            )
            return ConversationHandler.END

        notif_id = ObjectId(raw_id)
        NotificationConfig.update_text(notif_id, new_text)
        await update.message.reply_text(
            cfg.get_message("edited_text", default="Текст напоминания обновлён.")
        )
        context.user_data.pop("edit_id", None)
        return ConversationHandler.END

    # --- Шаг 8: получен новый интервал (после «Изменить интервал») ---
    @available_or_message
    @measure_duration("notification_edit_interval")
    async def perform_edit_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        interval_str = update.message.text.strip()
        cfg = CommandConfig.get("notifications")
        try:
            new_interval_seconds = _parse_interval_to_seconds(interval_str)
        except ValueError as e:
            errmsg = f"Неверный формат интервала: {e}. Повторите ввод HH:MM:SS"
            await update.message.reply_text(errmsg)
            return EDIT_INTERVAL

        raw_id = context.user_data.get("edit_id")
        if not raw_id:
            await update.message.reply_text(
                cfg.get_message("error_collecting_data", default="Не удалось найти напоминание.")
            )
            return ConversationHandler.END

        notif_id = ObjectId(raw_id)
        NotificationConfig.update_interval(notif_id, new_interval_seconds)
        await update.message.reply_text(
            cfg.get_message("edited_interval", default="Интервал напоминания обновлён.")
        )
        context.user_data.pop("edit_id", None)
        return ConversationHandler.END

    # --- Шаг 9: команда /cancel в любой момент диалога ---
    @available_or_message
    @measure_duration("notification_cancel")
    async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        cfg = CommandConfig.get("notifications")
        await update.message.reply_text(
            cfg.get_message("cancel", default="Действие отменено."), reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.pop("edit_id", None)
        context.user_data.pop("notif_text", None)
        return ConversationHandler.END

    # Сборка ConversationHandler с всеми entry_points и состояниями
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("create_notification", start_create),
            CommandHandler("notification_list", notification_list),
            CallbackQueryHandler(notification_list_callback, pattern=r"^notif_select:"),
            CallbackQueryHandler(notification_action_callback, pattern=r"^notif_action:")
        ],
        states={
            CREATE_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text)],
            CREATE_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_interval)],
            LIST_NOTIFY: [CallbackQueryHandler(notification_list_callback, pattern=r"^notif_select:")],
            EDIT_CHOICE: [CallbackQueryHandler(notification_action_callback, pattern=r"^notif_action:")],
            EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_edit_text)],
            EDIT_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_edit_interval)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True
    )

    return conv_handler
