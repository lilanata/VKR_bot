import logging
import time

import requests
from bs4 import BeautifulSoup, Tag
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.db import insert
from core.models.command_config import CommandConfig
from utils.check_utils import available_or_message, measure_duration

logger = logging.getLogger(__name__)


def contacts():
    """
    /contacts — парсинг телефонного справочника ПГУ и вывод всех контактных данных.
    """

    @available_or_message
    @measure_duration("contacts")
    async def _contacts(update: Update, context: ContextTypes.DEFAULT_TYPE):
        insert("data", {
            "type": "command",
            "command": "contacts",
            "timestamp": time.time()
        })
        cfg = CommandConfig.get("contacts")

        status_msg = await update.message.reply_text(cfg.get_message("contacts_data"))

        try:
            # 1) Скачиваем страницу телефонного справочника ПГУ
            resp = requests.get("https://pnzgu.ru/telspr", timeout=15)
            resp.raise_for_status()
            html = resp.text

            # 2) Парсим HTML через BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            # Ищем элемент <h1> с «Телефонный справочник»
            h1 = soup.find(lambda tag: tag.name == "h1" and "Телефонный справоч" in tag.get_text())
            if not h1:
                # если страница изменится
                raise RuntimeError("Заголовок «Телефонный справочник» не найден на странице.")

            # Берём контейнер, в котором находится <h1>
            container = h1.parent

            # Собираем «сырые» строки (raw_lines) вместе с тегом <b> для заголовков
            raw_lines = []
            header_text = h1.get_text(strip=True)
            if header_text:
                # Отмечаем заголовок тегом <b> для дальнейшей обработки
                raw_lines.append(f"<b>{header_text}</b>")

            # 3) Проходим по всем след. siblings контейнера до появления футера
            for element in container.next_siblings:
                if not isinstance(element, Tag):
                    continue
                tag_name = element.name.lower()

                # Если встретили <footer> или блок с классом 'footer' — выходим из цикла
                if tag_name == "footer" or "footer" in (element.get("class") or []):
                    break

                # Заголовки h2–h4
                if tag_name in ("h2", "h3", "h4"):
                    txt = element.get_text(strip=True)
                    if txt:
                        raw_lines.append(f"<b>{txt}</b>")
                    continue

                # Абзацы <p>
                if tag_name == "p":
                    txt = element.get_text(separator=" ", strip=True)
                    if txt:
                        raw_lines.append(txt)
                    continue

                # Таблицы <table>
                if tag_name == "table":
                    for tr in element.find_all("tr"):
                        cells = []
                        for cell in tr.find_all(("th", "td")):
                            cell_text = cell.get_text(separator=" ", strip=True)
                            if cell_text:
                                cells.append(cell_text)
                        if cells:
                            raw_lines.append(" | ".join(cells))
                    continue

                # Списки <ul> и <ol>
                if tag_name in ("ul", "ol"):
                    for li in element.find_all("li"):
                        li_text = li.get_text(separator=" ", strip=True)
                        if li_text:
                            raw_lines.append(f"• {li_text}")
                    continue

                # Прочие <div> контейнеры: рекурсивно внутри них ищем такие же элементы
                if tag_name == "div":
                    for sub in element.descendants:
                        if not isinstance(sub, Tag):
                            continue
                        sub_name = sub.name.lower()

                        if sub_name in ("h2", "h3", "h4"):
                            txt = sub.get_text(strip=True)
                            if txt:
                                raw_lines.append(f"<b>{txt}</b>")
                        elif sub_name == "p":
                            txt = sub.get_text(separator=" ", strip=True)
                            if txt:
                                raw_lines.append(txt)
                        elif sub_name == "table":
                            for tr in sub.find_all("tr"):
                                cells = []
                                for cell in tr.find_all(("th", "td")):
                                    cell_text = cell.get_text(separator=" ", strip=True)
                                    if cell_text:
                                        cells.append(cell_text)
                                if cells:
                                    raw_lines.append(" | ".join(cells))
                        elif sub_name in ("ul", "ol"):
                            for li in sub.find_all("li"):
                                li_text = li.get_text(separator=" ", strip=True)
                                if li_text:
                                    raw_lines.append(f"• {li_text}")

            if len(raw_lines) <= 1:
                raise RuntimeError("Не удалось распознать содержимое телефонного справочника.")  # если нет содержимого

            # 4) Преобразуем «сырые» строки в HTML-формат для Telegram
            formatted_lines = []
            section_open = False  # флаг: открыт ли раздел

            for raw in raw_lines:
                # Получаем «плоский» текст без HTML-тегов
                plain = BeautifulSoup(raw, "lxml").get_text().strip()

                # Если raw заключён в <b>…</b>, считаем это «заголовком секции»
                if raw.startswith("<b>") and raw.endswith("</b>"):
                    # Вставляем пустую строку, если это не первый заголовок
                    if section_open:
                        formatted_lines.append("")  # пустая линия между разделами
                    # Делаем заголовок жирным через <b>…</b>
                    formatted_lines.append(f"<b>{plain}</b>")
                    formatted_lines.append("")  # пустая строка после заголовка для визуального отступа
                    section_open = True
                    continue

                # Если строка содержит « | », разбираем на части
                if " | " in plain:
                    parts = [p.strip() for p in plain.split("|")]

                    # Если это строка «Ректорат | Внутр. | Город.», выводим заголовок подраздела «Ректорат»
                    if parts[0].startswith("Ректорат") and len(parts) == 3:
                        if section_open:
                            formatted_lines.append("")  # разделяем предыдущий и текущий блок
                        formatted_lines.append(f"<b>Ректорат</b>")  # жирный заголовок подраздела
                        formatted_lines.append("")  # пустая строка
                        continue

                    # Если три колонки (Напр., Ректорат | Внутр. | Город.), выводим с пояснением
                    if len(parts) == 3:
                        label, inner_num, city_num = parts
                        formatted_lines.append(f"• <b>{label}</b> (Внт.: {inner_num}, Гор.: {city_num})")
                    elif len(parts) == 2:
                        # Обычный «метка | значение»
                        label, value = parts
                        formatted_lines.append(f"• <b>{label}</b>: {value}")
                    else:
                        # На всякий случай — объединяем всё
                        formatted_lines.append(f"• {plain}")
                else:
                    # Если нет « | », просто выводим как пункт маркированного списка
                    formatted_lines.append(f"• {plain}")

            # Убираем лишние пустые строки в начале и конце
            while formatted_lines and not formatted_lines[0].strip():
                formatted_lines.pop(0)
            while formatted_lines and not formatted_lines[-1].strip():
                formatted_lines.pop()

            # Собираем всё в одну строку с переводами строк
            full_html = "\n".join(formatted_lines)

            # 5) Разбиваем на чанки (~4000 символов), чтобы не превысить лимит Telegram
            chunks = []
            max_len = 4000
            while full_html:
                if len(full_html) <= max_len:
                    chunks.append(full_html)
                    break
                # Ищем последний перенос строки перед границей
                split_pos = full_html.rfind("\n", 0, max_len)
                if split_pos == -1:
                    split_pos = max_len
                part = full_html[:split_pos]
                chunks.append(part)
                full_html = full_html[split_pos:].lstrip("\n")

            await status_msg.delete()
            for chunk in chunks:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML)

        except Exception as ex:
            logger.exception("Ошибка при выполнении /contacts")
            try:
                await status_msg.edit_text(cfg.get_message("error_collecting_data"))
            except Exception:
                await update.message.reply_text(cfg.get_message("error_collecting_data"))

    return _contacts
