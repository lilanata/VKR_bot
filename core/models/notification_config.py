import time
from copy import deepcopy
from typing import Dict, Any, List

from bson import ObjectId

from core import db
from core.templates import notification_template

collection_name = "notifications"


class NotificationConfig:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: ObjectId = data["_id"]
        self.user_id: int = data.get("user_id", 0)
        self.text: str = data.get("text", "")
        self.interval: int = data.get("interval", 0)  # в секундах
        self.next_run: int = data.get("next_run", 0)  # unix timestamp
        self.enabled: bool = data.get("enabled", True)

    def __repr__(self) -> str:
        return (
            f"NotificationConfig(id={self.id}, user_id={self.user_id}, "
            f"text={self.text!r}, interval={self.interval}, next_run={self.next_run}, "
            f"enabled={self.enabled})"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "text": self.text,
            "interval": self.interval,
            "next_run": self.next_run,
            "enabled": self.enabled
        }

    @classmethod
    def create(cls, user_id: int, text: str, interval_seconds: int) -> "NotificationConfig":
        """
        Создать новое напоминание: устанавливает next_run = сейчас + interval_seconds.
        """
        data = deepcopy(notification_template)
        data["user_id"] = user_id
        data["text"] = text
        data["interval"] = interval_seconds
        now_ts = int(time.time())
        data["next_run"] = now_ts + interval_seconds
        data["enabled"] = True
        db.insert(collection_name, data)
        return cls(data)

    @classmethod
    def get(cls, notif_id: ObjectId) -> "NotificationConfig":
        """
        Получить одно напоминание по ObjectId.
        """
        data: Dict[str, Any] = db.find_one(collection_name, {"_id": notif_id})
        if not data:
            raise ValueError(f"Напоминание с id={notif_id} не найдено.")
        return cls(data)

    @classmethod
    def get_all_for_user(cls, user_id: int) -> List["NotificationConfig"]:
        """
        Вернуть все напоминания конкретного пользователя.
        """
        docs = db.find(collection_name, {"user_id": user_id})
        return [cls(doc) for doc in docs]

    @classmethod
    def update_text(cls, notif_id: ObjectId, new_text: str) -> "NotificationConfig":
        """
        Обновить текст напоминания.
        """
        db.update_one(collection_name, {"_id": notif_id}, {"$set": {"text": new_text}})
        return cls.get(notif_id)

    @classmethod
    def update_interval(cls, notif_id: ObjectId, new_interval_seconds: int) -> "NotificationConfig":
        """
        Обновить интервал: сохраняем новый interval и пересчитываем next_run = now + interval.
        """
        now_ts = int(time.time())
        new_next = now_ts + new_interval_seconds
        db.update_one(
            collection_name,
            {"_id": notif_id},
            {"$set": {"interval": new_interval_seconds, "next_run": new_next}}
        )
        return cls.get(notif_id)

    @classmethod
    def toggle_enabled(cls, notif_id: ObjectId, enable: bool) -> "NotificationConfig":
        """
        Включить/выключить напоминание.
        """
        db.update_one(collection_name, {"_id": notif_id}, {"$set": {"enabled": enable}})
        return cls.get(notif_id)

    @classmethod
    def delete(cls, notif_id: ObjectId) -> None:
        """
        Удалить напоминание из БД.
        """
        db.delete_one(collection_name, {"_id": notif_id})
