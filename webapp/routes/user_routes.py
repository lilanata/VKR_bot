import logging
import os

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort

from core.models import users
from services.encryption import EncryptionService
from . import login_required

logger = logging.getLogger(__name__)
users_bp = Blueprint("users", __name__)


def teacher_forbidden():
    if g.current_user and g.current_user.role == 'teacher':
        abort(403)


@users_bp.route("/", methods=["GET"])
@login_required
def view_users():
    users_list = users.custom_select({})
    read_only = False
    if g.current_user and g.current_user.role == 'teacher':
        read_only = True
    return render_template("users.html", users_list=users_list, read_only=read_only)


@users_bp.route("/update", methods=["POST"])
@login_required
def update_user():
    try:
        teacher_forbidden()
        telegram_id = request.form.get('telegram_id')
        if not telegram_id:
            flash("Не указан идентификатор пользователя", "error")
            return redirect(url_for("users.view_users"))

        user = users.select_user(int(telegram_id))
        if not user:
            flash("Пользователь не найден", "error")
            return redirect(url_for("users.view_users"))

        has_changes = False

        mappings = {
            'telegram_username': 'telegram_username',
            'email': 'email',
            'role': 'role',
            'faculty': 'faculty',
            'course': 'course',
            'group': 'group',
            'education_level': 'education_level',
            'study_form': 'study_form'
        }
        for form_key, attr in mappings.items():
            new_val = request.form.get(form_key) or None
            if getattr(user, attr) != new_val:
                setattr(user, attr, new_val)
                has_changes = True

        new_notif = bool(request.form.get('notifications_enabled'))
        if getattr(user, 'notifications', None) != new_notif:
            user.notifications = new_notif
            has_changes = True

        new_password = request.form.get('password')
        if new_password != "":
            encryptor = EncryptionService(os.getenv("ENCRYPTION_KEY"))
            new_password = encryptor.encrypt(new_password)
            if getattr(user, 'password', None) != new_password:
                user.password = new_password
                has_changes = True

        if has_changes:
            flash(f"Данные пользователя {user.telegram_username} успешно обновлены", "info")
        else:
            flash("Нет изменений для сохранения", "info")

    except ValueError as e:
        flash(f"Ошибка формата данных: {str(e)}", "error")
    except Exception as e:
        logger.error(f"Ошибка при обновлении пользователя: {str(e)}")
        flash("Произошла ошибка при обновлении", "error")

    return redirect(url_for("users.view_users"))


@users_bp.route("/delete", methods=["POST"])
@login_required
def delete_user():
    try:
        teacher_forbidden()
        telegram_id = request.form.get('telegram_id')
        if not telegram_id:
            flash("Не указан идентификатор пользователя", "error")
            return redirect(url_for("users.view_users"))

        user = users.select_user(int(telegram_id))
        if not user:
            flash("Пользователь не найден", "error")
            return redirect(url_for("users.view_users"))

        users.remove_user(int(telegram_id))

        flash(f"Пользователь удален", "info")

    except ValueError as e:
        flash(f"Ошибка формата данных: {str(e)}", "error")
    except Exception as e:
        logger.error(f"Ошибка при обновлении пользователя: {str(e)}")
        flash("Произошла ошибка при обновлении", "error")

    return redirect(url_for("users.view_users"))
