import time
from copy import deepcopy

from core import db, templates

collection_name = "users"


class User:
    def __init__(self, user):
        self._uuid = user.get("_id")
        self._telegram_id = user.get("telegram_id")
        self._telegram_username = user.get("telegram_username")
        self._email = user.get("email")
        self._password = user.get("password")
        self._created = user.get("created")
        self._notifications = user.get("notifications")
        self._education_level = user.get("education_level")
        self._study_form = user.get("study_form")
        self._faculty = user.get("faculty")
        self._course = user.get("course")
        self._group = user.get("group")
        self._group_list = user.get("group_list")
        self._role = user.get("role")

    @property
    def uuid(self): return self._uuid

    @property
    def telegram_id(self): return self._telegram_id

    @property
    def telegram_username(self): return self._telegram_username

    @property
    def email(self): return self._email

    @property
    def password(self): return self._password

    @property
    def created(self): return self._created

    @property
    def notifications(self): return self._notifications

    @property
    def education_level(self): return self._education_level

    @property
    def study_form(self): return self._study_form

    @property
    def faculty(self): return self._faculty

    @property
    def course(self): return self._course

    @property
    def group(self): return self._group

    @property
    def group_list(self): return self._group_list

    @property
    def role(self): return self._role

    @telegram_id.setter
    def telegram_id(self, value):
        self._telegram_id = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"telegram_id": value}})

    @telegram_username.setter
    def telegram_username(self, value):
        self._telegram_username = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"telegram_username": value}})

    @email.setter
    def email(self, value):
        self._email = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"email": value}})

    @password.setter
    def password(self, value):
        self._password = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"password": value}})

    @notifications.setter
    def notifications(self, value):
        self._notifications = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"notifications": value}})

    @education_level.setter
    def education_level(self, value):
        self._education_level = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"education_level": value}})

    @study_form.setter
    def study_form(self, value):
        self._study_form = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"study_form": value}})

    @faculty.setter
    def faculty(self, value):
        self._faculty = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"faculty": value}})

    @course.setter
    def course(self, value):
        self._course = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"course": value}})

    @group.setter
    def group(self, value):
        self._group = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"group": value}})

    @group_list.setter
    def group_list(self, value):
        self._group_list = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"group_list": value}})

    @role.setter
    def role(self, value):
        self._role = value
        db.update_one(collection_name, {"telegram_id": self.telegram_id}, {"$set": {"role": value}})


def _get_user(telegram_id):
    return db.find_one(collection_name, {"telegram_id": telegram_id})


def exist(telegram_id):
    return _get_user(telegram_id) is not None if True else False


def create_user(telegram_id, telegram_username, group):
    telegram_id = telegram_id
    telegram_username = str(telegram_username)

    template = deepcopy(templates.user_template)
    template["telegram_id"] = telegram_id
    template["telegram_username"] = telegram_username
    template["group"] = group
    template["created"] = time.time()

    db.insert(collection_name, template)
    db.insert("data", {"type": "new_user", "timestamp": time.time()})
    return select_user(telegram_id)


def select_user(telegram_id) -> User:
    try:
        return User(_get_user(telegram_id))
    except TypeError:
        return None


def custom_select(request):
    return map(User, db.find(collection_name, request))


def remove_user(telegram_id) -> None:
    db.delete_one(collection_name, {"telegram_id": telegram_id})
