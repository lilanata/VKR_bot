import time
import datetime
from functools import wraps

from flask import session, redirect, url_for, g

from core.db import get_collection


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in") and not session.get("role"):
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated


from .auth_routes import auth_bp
from .dashboard_routes import main_bp
from .user_routes import users_bp
from .check_routes import check_bp
from .settings_routes import settings_bp
from .logs_routes import logs_bp
from .questions_routes import questions_bp
from .materials_routes import materials_bp
from .announcements_routes import announcements_bp


def get_plural(n, forms):
    """
    Универсальная функция для выбора правильной формы слова в русском языке.
    forms – кортеж из трех форм, например:
    ('минута', 'минуты', 'минут')
    """
    n = abs(n) % 100
    n1 = n % 10
    if 10 < n < 20:
        return forms[2]
    if 1 < n1 < 5:
        return forms[1]
    if n1 == 1:
        return forms[0]
    return forms[2]


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(users_bp, url_prefix="/users")
    app.register_blueprint(check_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(logs_bp, url_prefix="/logs")
    app.register_blueprint(questions_bp)
    app.register_blueprint(materials_bp)
    app.register_blueprint(announcements_bp)

    @app.template_filter('datetimeformat')
    def datetimeformat(timestamp):
        return datetime.datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')

    @app.template_filter('timesince')
    def timesince(timestamp):
        """
        Выводит относительный промежуток времени от переданного timestamp до «сейчас»:
        < 60 секунд    → «N секунд назад»
        < 60 минут     → «N минут назад»
        < 24 часов     → «N часов назад»
        < 30 дней      → «N дней назад»
        Иначе          → просто дата «DD.MM.YYYY»
        """
        now = datetime.datetime.now()
        try:
            dt = datetime.datetime.fromtimestamp(timestamp)
        except Exception:
            return ""
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 60:
            count = seconds
            form = get_plural(count, ('секунда', 'секунды', 'секунд'))
            return f"{count} {form} назад"

        minutes = seconds // 60
        if minutes < 60:
            count = minutes
            form = get_plural(count, ('минута', 'минуты', 'минут'))
            return f"{count} {form} назад"

        hours = minutes // 60
        if hours < 24:
            count = hours
            form = get_plural(count, ('час', 'часа', 'часов'))
            return f"{count} {form} назад"

        days = hours // 24
        if days < 30:
            count = days
            form = get_plural(count, ('день', 'дня', 'дней'))
            return f"{count} {form} назад"

        return dt.strftime('%d.%m.%Y')

    @app.context_processor
    def inject_user_role():
        return {
            "current_role": getattr(g.current_user, "role", None),
            "current_user": g.current_user
        }

    @app.context_processor
    def inject_common():
        """
        Прокидывает в шаблоны:
         - admin: имя администратора
         - session_time: сколько админ в сессии
         - authorizations_on_site: сколько логинов на сайте
        """
        admin = session.get("admin_username")
        session_time = None
        if session.get("login_time"):
            seconds = int(time.time() - session["login_time"])
            h, m, s = seconds // 3600, (seconds % 3600) // 60, seconds % 60
            session_time = f"{h}:{m:02}:{s:02}" if h > 0 else f"{m}:{s:02}"

        data_coll = get_collection("data")
        authorizations_on_site = data_coll.count_documents({"type": "authorization_on_site"})

        return dict(
            admin=admin,
            session_time=session_time,
            authorizations_on_site=authorizations_on_site
        )
