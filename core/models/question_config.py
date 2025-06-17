import time
from copy import deepcopy
from typing import Dict, Any, List

from bson import ObjectId

from core import db
from core.templates import question_template

collection_name = "questions"


class QuestionConfig:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: ObjectId = data["_id"]
        self.tg_username: str = data.get("tg_username", "")
        self.tg_id: str = data.get("tg_id", "")
        self.teacher: str = data.get("teacher", "")
        self.question: str = data.get("question", "")
        self.answer: str = data.get("answer", "")
        self.state: str = data.get("state", "")
        self.created: int = data.get("created", 0)

    def __repr__(self) -> str:
        return (
            f"QuestionConfig(id={self.id}, "
            f"tg_username={self.tg_username!r}, "
            f"tg_id={self.tg_id!r}, "
            f"teacher={self.teacher!r}, "
            f"answer={self.answer!r}, "
            f"state={self.state!r}, "
            f"created={self.created})"
        )

    def __dict__(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "tg_username": self.tg_username,
            "tg_id": self.tg_id,
            "teacher": self.teacher,
            "question": self.question,
            "answer": self.answer,
            "state": self.state,
            "created": self.created,
        }

    @classmethod
    def update_answer_and_state(cls, oid, answer_text, new_state):
        db.update_one(collection_name,
            {"_id": oid},
            {"$set": {"answer": answer_text, "state": new_state, "answered_ts": time.time()}}
        )

    @classmethod
    def create(cls, tg_username: str, tg_id: str, teacher: str, question: str, state: str) -> "QuestionConfig":
        """
        Создаёт новый документ в коллекции questions и возвращает его обёртку.
        """
        data = deepcopy(question_template)
        data["tg_username"] = tg_username
        data["tg_id"] = tg_id
        data["teacher"] = teacher
        data["question"] = question
        data["state"] = state
        data["created"] = int(time.time())
        # Вставляем в MongoDB
        db.insert(collection_name, data)
        # В отличие от CommandConfig.get, здесь явно знаем, что создали новый
        return cls(data)

    @classmethod
    def get(cls, question_id: ObjectId) -> "QuestionConfig":
        """
        Загрузить вопрос по ObjectId.
        """
        data: Dict[str, Any] = db.find_one(collection_name, {"_id": question_id})
        if not data:
            raise ValueError(f"Вопрос с id={question_id} не найден.")
        return cls(data)

    @classmethod
    def get_all(cls, filter_dict: Dict[str, Any] = None) -> List["QuestionConfig"]:
        """
        Вернуть список всех вопросов (по необязательному фильтру).
        """
        if filter_dict is None:
            filter_dict = {}
        docs = db.find(collection_name, filter_dict)
        return [cls(doc) for doc in docs]

    @classmethod
    def update_state(cls, question_id: ObjectId, new_state: str) -> "QuestionConfig":
        """
        Обновить поле 'state' у существующего вопроса.
        """
        db.update_one(collection_name, {"_id": question_id}, {"$set": {"state": new_state}})
        return cls.get(question_id)

    @classmethod
    def delete(cls, question_id: ObjectId) -> None:
        """
        Удалить вопрос по ObjectId.
        """
        db.delete_one(collection_name, {"_id": question_id})
