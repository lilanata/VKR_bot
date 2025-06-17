import time

from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from core.models.question_config import QuestionConfig


# Команда /tracker — выводит список вопросов пользователя и их состояние
async def questions_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    tg_username = user.username or str(user.id)
    # Получаем все вопросы этого пользователя
    all_questions = QuestionConfig.get_all({"tg_username": tg_username})
    if not all_questions:
        await update.message.reply_text("У вас пока нет отправленных вопросов.")
        return

    lines = []
    for q in all_questions:
        # Ограничиваем текст вопроса до 100 символов (с «...» при необходимости)
        text = q.question
        preview = text if len(text) <= 100 else text[:97] + "..."
        # Время создания
        created_str = time.strftime("%d.%m.%Y %H:%M:%S", time.localtime(q.created))
        lines.append(f"\nВремя: {created_str}\nВопрос: {preview}\nСостояние: {convert_state(q.state)}\n")

    full_text = "\n".join(lines)
    max_len = 4000
    while full_text:
        if len(full_text) <= max_len:
            await update.message.reply_text(full_text)
            break
        split_pos = full_text.rfind("\n", 0, max_len)
        if split_pos == -1:
            split_pos = max_len
        part = full_text[:split_pos]
        await update.message.reply_text(part)
        full_text = full_text[split_pos:].lstrip("\n")


def convert_state(state: str) -> str:
    if state == "waiting":
        return "Ожидает ответа"
    if state == "answered":
        return "Ответил"
    if state == "closed":
        return "Закрыт"
    return state


def get_tracker_handler() -> CommandHandler:
    return CommandHandler("tracker", questions_tracker)
