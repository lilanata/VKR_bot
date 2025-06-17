import asyncio
import logging

from flask import Blueprint, render_template, request, redirect, flash, g, abort, current_app, url_for

from core.models import users
from . import login_required

logger = logging.getLogger(__name__)
announcements_bp = Blueprint("announcements", __name__)


def teacher_only():
    """
    Разрешаем доступ только тем, у кого роль 'teacher'.
    Иначе — 403 Forbidden.
    """
    if not getattr(g, "current_user", None) or g.current_user.role != "teacher":
        abort(403)


@announcements_bp.route("/announcements", methods=["GET", "POST"])
@login_required
def send_announcements():
    """
    GET:  Рендерим страницу с формой рассылки (группы + студенты).
    POST: Обрабатываем отправку — получаем выбранные группы и/или студентов,
          формируем список telegram_id и рассылаем сообщение через bot.
    """
    teacher_only()

    # --- 1. Забираем всех пользователей из БД ---
    all_users = list(users.custom_select({}))

    # --- 2. Собираем список уникальных групп (непустых) ---
    groups_set = {u.group for u in all_users if getattr(u, "group", None)}
    groups = sorted(groups_set)  # чтобы выводить отсортированный список

    # --- 3. Собираем список всех студентов (роль == 'student') ---
    students = [u for u in all_users if u.role == "student"]

    if request.method == "POST":
        # --- 4. Читаем из формы выбранные группы и список отдельных студентов ---
        selected_groups = request.form.getlist("groups")  # например, ['ИС-101', 'ПМИ-102']
        selected_students = request.form.getlist("students")  # тут будут строки с telegram_id
        message_text = request.form.get("message", "").strip()

        if not message_text:
            flash("Введите текст сообщения.", "error")
            return redirect(url_for("announcements.send_announcements"))

        recipients = set()

        # --- 4.1. Добавляем всех студентов из выбранных групп ---
        if selected_groups:
            for u in all_users:
                if u.role == "student" and u.group in selected_groups and u.telegram_id:
                    recipients.add(str(u.telegram_id))

        # --- 4.2. Добавляем индивидуально выбранных студентов ---
        if selected_students:
            for tid_str in selected_students:
                try:
                    tid = int(tid_str)
                except ValueError:
                    continue
                u_obj = users.select_user(tid)
                if u_obj and u_obj.telegram_id:
                    recipients.add(str(tid))

        if not recipients:
            flash("Нужно выбрать хотя бы одну группу или студента.", "error")
            return redirect(url_for("announcements.send_announcements"))

        # --- 5. Рассылаем сообщение каждому telegram_id ---
        success_count = 0
        fail_count = 0

        for tid_str in recipients:
            try:
                tid = int(tid_str)
                # Здесь делаем отправку через Telegram Bot (предполагается, что current_app.bot инициализирован)
                asyncio.run(current_app.bot.send_message(chat_id=tid, text=message_text))
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка при отправке сообщения пользователю {tid_str}: {e}")
                fail_count += 1

        flash(f"Сообщения отправлены: {success_count}. Ошибок: {fail_count}.", "info")
        return redirect(url_for("announcements.send_announcements"))

    # GET-запрос: просто рендерим страницу с группами и списком студентов
    return render_template(
        "announcements.html",
        groups=groups,
        students=students
    )
