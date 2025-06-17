import asyncio

import telegram
from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app

from core.models.question_config import QuestionConfig
from core.models.users import select_user

questions_bp = Blueprint("questions", __name__, template_folder="templates")


def current_role():
    user_id = session.get("user_telegram_id")
    if not user_id:
        return None
    user = select_user(user_id)
    return user.role if user else None


@questions_bp.route("/questions/<qid>/answer", methods=["POST"])
def answer_question(qid: str):
    answer_text = request.form.get("answer", "").strip()
    new_state = request.form.get("state", "").strip()

    if not answer_text:
        flash("Введите ответ и выберите корректный статус.", "error")
        return redirect(url_for("questions.view_questions"))

    try:
        oid = ObjectId(qid)
        q = QuestionConfig.get(oid)
    except Exception:
        flash("Вопрос не найден.", "error")
        return redirect(url_for("questions.view_questions"))

    QuestionConfig.update_answer_and_state(oid, answer_text, new_state)

    msg = (f"На ваш вопрос:\n«{q.question}»\n\n"
           f"получен ответ:\n{answer_text}\n\n"
           f"Новый статус: {new_state}")

    try:
        try:
            asyncio.run(current_app.bot.send_message(chat_id=q.tg_id, text=msg))
        except telegram.error.NetworkError:
            pass
        flash("Ответ отправлен студенту.", "info")
    except Exception as e:
        current_app.logger.exception("Не удалось отправить ТГ-сообщение: %s", e)
        flash("Ответ сохранён, но сообщение студенту не доставлено.", "warn")

    return redirect(url_for("questions.view_questions"))


@questions_bp.route("/questions", methods=["GET"])
def view_questions():
    role = current_role()
    questions = QuestionConfig.get_all()

    # Передаем в шаблон: список вопросов и флаг, преподаватель ли это
    return render_template(
        "questions.html",
        questions=[q.__dict__() for q in questions],
        is_teacher=(role == "teacher")
    )


@questions_bp.route("/questions/<q_id>/update", methods=["POST"])
def update_question(q_id):
    new_state = request.form.get("state", "").strip()
    try:
        oid = ObjectId(q_id)
        QuestionConfig.update_state(oid, new_state)
        flash("Статус вопроса обновлён.", "info")
    except Exception:
        flash("Не удалось обновить статус вопроса.", "error")

    return redirect(url_for("questions.view_questions"))
