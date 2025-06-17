import asyncio
import logging
from threading import Thread

from flask import Blueprint, flash, redirect, url_for

from scheduler import scheduled_check
from . import login_required

logger = logging.getLogger(__name__)
check_bp = Blueprint("check", __name__)


@check_bp.route("/run-check", methods=["POST"])
@login_required
def run_check():
    def worker():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(scheduled_check(None))
        finally:
            loop.close()

    Thread(target=worker, daemon=True).start()
    flash("✅ Ручная проверка уведомлений запущена", "info")
    return redirect(url_for("main.root"))
