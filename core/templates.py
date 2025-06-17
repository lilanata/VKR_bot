user_template = {
    "telegram_id": None,
    "telegram_username": None,
    "email": None,
    "password": None,
    "created": 0,
    "notifications": True,
    "education_level": None,
    "study_form": None,
    "faculty": None,
    "course": None,
    "group": None,
    "group_list": [],
    "role": "user"
}

command_config_template = {
    "name": "config",
    "info": None,
    "command": None,
    "messages": {}
}

question_template = {
    "tg_username": None,
    "tg_id": None,
    "teacher": None,
    "question": None,
    "answer": None,
    "state": None,
    "created": 0
}

notification_template = {
    "user_id": None,
    "text": None,
    "interval": 0,
    "next_run": 0,
    "enabled": True
}
