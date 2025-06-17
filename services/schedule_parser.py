import datetime
import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://pnzgu.ru/schedule"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}
TARGET_DIR = Path("../schedules").resolve()
TARGET_DIR.mkdir(exist_ok=True)
MAPPING_PATH = TARGET_DIR / "mapping.json"
GROUP_RE = re.compile(r"\b\d{2}[А-ЯA-Z]{1,3}[а-яА-ЯA-Za-z]?\d?\b")


def _find_fvt_study_links(html: str) -> List[str]:
    """Возвращает ровно 15 абсолютных ссылок .xls из блока «Факультет вычислительной техники / учебные занятия»."""
    soup = BeautifulSoup(html, "lxml")

    dept_div = soup.find(
        "div",
        class_="name_department spoiler-title",
        string=re.compile(r"Факультет вычислительной техники", re.I),
    )
    if not dept_div:
        raise RuntimeError("Не найден «Факультет вычислительной техники» на странице.")

    dept_body = dept_div.find_next("div", class_="spoiler-body")
    if not dept_body:
        raise RuntimeError("Структура страницы изменилась (dept spoiler-body).")

    study_title = dept_body.find(
        "div",
        class_="type_sh spoiler-title",
        string=re.compile(r"учебные занятия", re.I),
    )
    if not study_title:
        raise RuntimeError("Не найден раздел «учебные занятия».")

    study_body = study_title.find_next("div", class_="spoiler-body")
    if not study_body:
        raise RuntimeError("Структура страницы изменилась (study spoiler-body).")

    links = [
        (href if href.startswith("http") else f"https://pnzgu.ru{href}")
        for a in study_body.select("a.shedule_row_name_link[href$='.xls']")
        if (href := a.get("href"))
    ]
    if len(links) != 15:
        raise RuntimeError(f"Ожидалось 15 ссылок .xls, найдено {len(links)}.")
    return links


def _download_if_needed(url: str) -> Path:
    """Скачивает .xls по URL, если его ещё нет локально, возвращает Path."""
    fname = url.split("/")[-1]
    fpath = TARGET_DIR / fname
    if fpath.exists():
        return fpath

    print(f"→ Скачиваю {fname} . . .", end="", flush=True)
    with requests.get(url, stream=True, headers=HEADERS, timeout=30) as resp:
        resp.raise_for_status()
        with fpath.open("wb") as f:
            for chunk in resp.iter_content(8192):
                if chunk:
                    f.write(chunk)
    print(" ГОТОВО")
    return fpath


def _refresh_schedule_files() -> List[Path]:
    """Обновляет локальную папку ../schedules: скачивает все 15 .xls и возвращает список их Path."""
    print(f"Каталог загрузки: {TARGET_DIR}")
    html = requests.get(BASE_URL, headers=HEADERS, timeout=30).text
    links = _find_fvt_study_links(html)
    paths: List[Path] = []
    for u in links:
        try:
            p = _download_if_needed(u)
            paths.append(p)
        except Exception as e:
            print(f"Ошибка при скачивании {u}: {e}")
    return paths


def _extract_groups_from_xls(xls_path: Path) -> Set[str]:
    """Читает .xls (xls_path) и собирает множество всех групп (кодов вида «23ВВВ2» и т.п.)."""
    groups: Set[str] = set()
    try:
        xl = pd.ExcelFile(xls_path, engine="xlrd")
    except Exception:
        return groups

    for sheet in xl.sheet_names:
        try:
            df = xl.parse(sheet, header=None, dtype=str)
        except Exception:
            continue
        for val in df.values.ravel():
            if isinstance(val, str):
                for m in GROUP_RE.findall(val):
                    groups.add(m.upper())
    return groups


def _build_mapping(xls_paths: List[Path]) -> Dict[str, List[str]]:
    """
    Создаёт новый mapping.json:
      ключ — имя файла (str),
      значение — список всех групп (List[str]), найденных в этом файле.
    """
    print("Строю новый mapping.json . . .")
    mapping: Dict[str, List[str]] = {}
    for p in xls_paths:
        gr = sorted(_extract_groups_from_xls(p))
        mapping[p.name] = gr
        print(f"  {p.name:<30} → {', '.join(gr) or '‹нет групп›'}")
    with MAPPING_PATH.open("w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print("✓ mapping.json сохранён.")
    return mapping


def _load_or_create_mapping(force_rebuild: bool = False) -> Dict[str, List[str]]:
    """
    Возвращает mapping (имя_файла → список групп).
    Если force_rebuild=True, всегда пересоздаёт файл mapping.json.
    Иначе, проверяет дату изменения XLS-файлов и mapping.json и при необходимости пересоздаёт.
    """
    xls_paths = _refresh_schedule_files()
    if force_rebuild or not MAPPING_PATH.exists():
        return _build_mapping(xls_paths)

    mp_mtime = MAPPING_PATH.stat().st_mtime
    need_rebuild = False
    for p in xls_paths:
        if p.stat().st_mtime > mp_mtime:
            need_rebuild = True
            break

    if need_rebuild:
        return _build_mapping(xls_paths)

    with MAPPING_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _detect_semester_by_date(filename: str) -> Optional[str]:
    """
    Определяет семестр по дате в имени файла: '<идентификатор>-DDMMYYYYhhmmss.xls'.
    Если месяц >= 9 или month <= 1 → считаем «первым семестром» (осенне-зимний),
    Иначе (month 2–8) → «другим семестром» (весенне-летний).
    """
    # Ищем часть после дефиса, первые 8 символов — DDMMYYYY
    m = re.search(r"-(\d{8})", filename)
    if not m:
        return None
    date_part = m.group(1)  # примерно '20022025'
    try:
        dt = datetime.datetime.strptime(date_part, "%d%m%Y").date()
    except ValueError:
        return None

    month = dt.month
    # Осенне-зимний: сентябрь (9), октябрь (10), ноябрь (11), декабрь (12), январь (1)
    if month >= 9 or month == 1:
        return "первый"
    # Весенне-летний: февраль–август
    return "другой"


def find_semester_files(group: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Для переданной группы возвращает два пути:
      (path_first_semester, path_other_semester).
    Первый семестр — файлы, дата которых в имени попадает в осенне-зимний период (мес. ≥ 9 или = 1),
    Второй («другой») — весенне-летний (мес. от 2 до 8).
    Если какой-то файл не найден, возвращается None на месте.
    """
    # Принудительно пересоздаём mapping, чтобы учесть новые файлы
    mapping = _load_or_create_mapping(force_rebuild=True)

    first_path: Optional[Path] = None
    other_path: Optional[Path] = None

    print(f"Ищем группу «{group}» в следующих файлах:")
    for fname, groups in mapping.items():
        if group.upper() not in groups:
            continue

        sem = _detect_semester_by_date(fname)
        print(f"  → группа найдена в файле '{fname}', определён семестр = {sem!r}")

        if sem == "первый" and first_path is None:
            first_path = TARGET_DIR / fname
        elif sem == "другой" and other_path is None:
            other_path = TARGET_DIR / fname

        # Продолжаем обход до конца, чтобы попытаться найти оба семестра

    if first_path:
        print(f"  --> найден файл «первого» семестра: {first_path.name}")
    else:
        print("  --> Файл «первого» семестра не найден")

    if other_path:
        print(f"  --> найден файл «другого» семестра: {other_path.name}")
    else:
        print("  --> Файл «другого» семестра не найден")

    return first_path, other_path


def start_parse(group: str) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Возвращает кортеж (path_first_semester, path_other_semester) для группы `group`.
    Если оба пути None — выбрасывает ValueError.
    """
    sem1, sem2 = find_semester_files(group)
    if sem1 is None and sem2 is None:
        raise ValueError(f"Группа «{group}» не найдена ни в одном семестре.")
    return sem1, sem2
