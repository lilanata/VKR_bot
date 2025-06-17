import logging
import time

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, CommandHandler, filters

from core.db import insert
from core.models.command_config import CommandConfig
from core.models.question_config import QuestionConfig
from core.models.users import select_user
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)

ASKING_TEACHER = 1
ASKING_QUESTION = 2


def questions():
    @available_or_message
    @measure_duration("questions_start")
    async def start_asking(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_telegram_id = update.effective_user.id
        user = select_user(user_telegram_id)
        cfg = CommandConfig.get("questions")

        if not user or not user.group:
            await update.message.reply_text(cfg.get_message("no_group"))
            return ConversationHandler.END

        insert("data", {
            "type": "command",
            "command": "questions",
            "timestamp": time.time()
        })

        # Запрашиваем фамилию преподавателя
        msg = cfg.get_message("ask_teacher", default="Укажите фамилию преподавателя, к которому адресован вопрос:")
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
        return ASKING_TEACHER

    @available_or_message
    @measure_duration("questions_receive_teacher")
    async def receive_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
        teacher = update.message.text.strip()
        cfg = CommandConfig.get("questions")

        if not teacher:
            await update.message.reply_text(cfg.get_message("empty_teacher"))
            return ASKING_TEACHER

        # Сохраняем преподавателя в context для использования на следующем шаге
        context.user_data['teacher'] = teacher

        # Запрашиваем текст вопроса
        msg = cfg.get_message("prompt_question", default="Теперь напишите ваш вопрос:")
        await update.message.reply_text(msg)
        return ASKING_QUESTION

    @available_or_message
    @measure_duration("questions_receive")
    async def receive_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = CommandConfig.get("questions")

        # Получаем сохраненного преподавателя из context
        teacher = context.user_data.get('teacher', '')
        if not teacher:
            await update.message.reply_text("Ошибка: преподаватель не указан")
            return ConversationHandler.END

        # Получаем текст вопроса
        question_text = update.message.text.strip()
        if not question_text:
            await update.message.reply_text(cfg.get_message("empty_question"))
            return ASKING_QUESTION

        # Сохраняем вопрос в БД
        QuestionConfig.create(
            tg_username=update.effective_user.username,
            tg_id=str(update.effective_user.id),
            teacher=teacher,
            question=question_text,
            state="Ожидает ответа"
        )

        # Уведомляем пользователя
        await update.message.reply_text(cfg.get_message("question_received"))

        # Очищаем временные данные
        context.user_data.pop('teacher', None)

        return ConversationHandler.END

    @available_or_message
    @measure_duration("questions_cancel")
    async def cancel_asking(update: Update, context: ContextTypes.DEFAULT_TYPE):
        cfg = CommandConfig.get("questions")
        # Очищаем временные данные при отмене
        context.user_data.pop('teacher', None)
        await update.message.reply_text(cfg.get_message("cancel"), reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("questions", start_asking)],
        states={
            ASKING_TEACHER: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_teacher)],
            ASKING_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_question)]
        },
        fallbacks=[CommandHandler("cancel", cancel_asking)],
        allow_reentry=True,
    )

    return conv_handler
