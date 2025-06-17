import asyncio
import logging
import time

from telegram.ext import Application

from core import db
from core.db import insert
from core.models.config import get_scheduled_enabled, get_schedule_interval
from core.models.notification_config import NotificationConfig

logger = logging.getLogger(__name__)
bot_object = None

async def scheduled_check(app: Application):
    """
    Функция проверяет коллекцию notifications и отправляет напоминания,
    у которых next_run <= сейчас и enabled == True.
    """
    global bot_object
    if bot_object is None:
        bot_object = app
    if not get_scheduled_enabled():
        return

    # Собираем статку для записи в БД
    start_wall = time.time()
    now_ts = int(time.time())
    to_send = db.find("notifications", {"enabled": True, "next_run": {"$lte": now_ts}})
    total_tasks = len(to_send)
    users_with_tasks = {t["user_id"] for t in to_send}
    total_users_with_tasks = len(users_with_tasks)
    logger.info(f"Найдено {total_tasks} напоминаний для отправки")
    start_ts = time.perf_counter()

    logger.info("=== НАЧАЛО ПРОВЕРКИ УВЕДОМЛЕНИЙ ===")

    # Для каждого уведомления: отправляем сообщение пользователю, обновляем next_run
    for notif in to_send:
        try:
            chat_id = notif["user_id"]
            # Отправляем напоминание (текст без форматирования)
            interval_sec = notif["interval"]
            hours = interval_sec // 3600
            minutes = (interval_sec % 3600) // 60
            seconds = interval_sec % 60
            next_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Сообщение пользователю
            message_text = (
                "Напоминание:\n"
                f"{notif["text"]}\n\n"
                "Следующее напоминание через:\n"
                f"{next_str}"
            )
            await bot_object.bot.send_message(chat_id=chat_id, text=message_text)

            # Обновляем next_run = now + interval
            NotificationConfig.update_interval(notif["_id"], notif["interval"])

        except Exception as e:
            logger.exception(f"Ошибка при отправке уведомления {notif["_id"]}: {e}")

    elapsed = time.perf_counter() - start_ts
    end_wall = time.time()
    logger.info(f"=== ПРОВЕРКА ЗАВЕРШЕНА (за {elapsed:.2f} с) ===")

    # Запишем статистику
    insert("data", {
        "type": "scheduled_check",
        "start_ts": start_wall,
        "end_ts": end_wall,
        "duration": elapsed,
        "total_tasks": total_tasks,
        "users_with_tasks": total_users_with_tasks
    })


async def background_check(app: Application):
    """
    Запуск фонового цикла: каждую минуту вызываем scheduled_check.
    """
    await asyncio.sleep(5)

    while True:
        await scheduled_check(app)
        await asyncio.sleep(get_schedule_interval() * 60)
