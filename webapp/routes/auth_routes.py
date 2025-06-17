import os
import time

from bson import ObjectId
from flask import Blueprint, request, session, redirect, url_for, flash, render_template, g

from core.db import find_one, insert
from core.models.users import User
from services.encryption import EncryptionService

auth_bp = Blueprint("auth", __name__)


@auth_bp.before_app_request
def load_current_user():
    """
    Перед каждым запросом пытаемся загрузить текущего пользователя.
    Если это админ (по флагу в session), ставим g.is_admin=True.
    Если это обычный, достаём из БД по user_id из session.
    """
    g.current_user = None
    g.is_admin = False

    if session.get("admin_logged_in"):
        g.is_admin = True
        g.current_user = None
    elif session.get("user_id"):
        try:
            # session["user_id"] хранится как строка, приводим к ObjectId
            user_oid = ObjectId(session["user_id"])
        except Exception:
            g.current_user = None
            return

        user_doc = find_one("users", {"_id": user_oid})
        if user_doc:
            g.current_user = User(user_doc)
        else:
            g.current_user = None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    1) Сначала пробуем админскую пару из переменных окружения.
    2) Если не админ, ищем в коллекции "users" по email.
       - Сравниваем password через EncryptionService.
    Если ни тот, ни другой не прошёл — показываем ошибку.
    """
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        # 1) Попытка авторизации как админ
        if username == os.getenv("ADMIN_USERNAME") and password == os.getenv("ADMIN_PASSWORD"):
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = username
            session["login_time"] = time.time()
            insert("data", {"type": "authorization_on_site", "timestamp": time.time()})
            return redirect(url_for("main.root"))

        # 2) Поиск пользователя в MongoDB по email (username)
        user_doc = find_one("users", {"email": username})
        if user_doc:
            key = os.getenv("ENCRYPTION_KEY", "")
            if not key:
                flash("Сбой сервиса: неподдерживаемый ключ шифрования.", "error")
                return render_template("login.html")

            encryptor = EncryptionService(key)
            try:
                decrypted = encryptor.decrypt(user_doc.get("password", ""))
            except Exception:
                flash("Ошибка сервиса шифрования.", "error")
                return render_template("login.html")

            if password == decrypted:
                session.clear()
                # Кладём в session строковое представление ObjectId
                session["user_id"] = str(user_doc.get("_id"))
                session["user_email"] = user_doc.get("email")
                session["user_telegram_id"] = user_doc.get("telegram_id")
                session["login_time"] = time.time()
                session["role"] = user_doc.get("role")
                insert("data", {"type": "authorization_on_site", "timestamp": time.time()})
                return redirect(url_for("main.root"))
            else:
                flash("Неверный пароль.", "error")
                return render_template("login.html")

        # Если не админ и не найден пользователь — общая ошибка
        flash("Неверный логин или пароль.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
