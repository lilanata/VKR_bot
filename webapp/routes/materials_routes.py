import os

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, g, current_app, send_from_directory, abort
)

from . import login_required

materials_bp = Blueprint("materials", __name__)


def teacher_only():
    """
    Проверка: пользователь должен быть залогинен и иметь роль 'teacher'.
    Иначе — 403.
    """
    if not g.current_user or getattr(g.current_user, "role", None) != 'teacher':
        abort(403)


def format_file_size(num_bytes):
    """
    Форматирование размера файла в человекочитаемый вид:
    B, KB, MB, GB и т.д.
    """
    if num_bytes < 1024:
        return f"{num_bytes} Б"
    for unit in ['КБ', 'МБ', 'ГБ', 'ТБ']:
        num_bytes /= 1024.0
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
    return f"{num_bytes:.1f} ТБ"


@materials_bp.route("/materials")
@login_required
def view_materials():
    """
    Показывает страницу публикации материалов.
    Если group не указан в параметрах запроса — выводим список всех папок-групп.
    Если group указан — показываем форму загрузки для выбранной группы и список файлов внутри этой группы.
    """
    teacher_only()

    # Корневая папка для материалов
    materials_root = os.path.join(current_app.root_path, "materials")
    # Создаём, если нет
    if not os.path.exists(materials_root):
        os.makedirs(materials_root)

    group = request.args.get("group")
    # Список всех существующих групп (подпапок)
    all_groups = [
        d for d in os.listdir(materials_root)
        if os.path.isdir(os.path.join(materials_root, d))
    ]

    if group:
        # Для выбранной группы создаём её папку, если не существует
        group_dir = os.path.join(materials_root, group)
        if not os.path.exists(group_dir):
            os.makedirs(group_dir)

        # Перечисляем файлы в папке группы и собираем информацию о размере
        raw_files = sorted(os.listdir(group_dir))
        files_info = []
        for filename in raw_files:
            file_path = os.path.join(group_dir, filename)
            try:
                size_bytes = os.path.getsize(file_path)
                human_size = format_file_size(size_bytes)
            except Exception:
                human_size = "–"
            files_info.append({
                'name': filename,
                'size': human_size
            })

        return render_template(
            "materials.html",
            groups=all_groups,
            selected_group=group,
            files=files_info
        )
    else:
        # Если группа не выбрана — просто показываем список групп
        return render_template(
            "materials.html",
            groups=all_groups,
            selected_group=None,
            files=None
        )


@materials_bp.route("/materials/upload", methods=["POST"])
@login_required
def upload_material():
    """
    Обрабатывает отправку файла преподавателем:
    - получает название группы и файл из формы,
    - сохраняет его в папку materials/<group>/.
    """
    teacher_only()

    group = request.form.get("group")
    file = request.files.get("file")

    if not group or not file:
        flash("Не указана группа или файл для загрузки", "error")
        return redirect(url_for("materials.view_materials"))

    materials_root = os.path.join(current_app.root_path, "materials")
    group_dir = os.path.join(materials_root, group)
    if not os.path.exists(group_dir):
        os.makedirs(group_dir)

    # Сохраняем файл с исходным именем
    filename = file.filename
    file_path = os.path.join(group_dir, filename)
    try:
        file.save(file_path)
        flash("Файл успешно загружен", "info")
    except Exception as e:
        flash(f"Ошибка при сохранении файла: {str(e)}", "error")

    return redirect(url_for("materials.view_materials", group=group))


@materials_bp.route("/materials/delete", methods=["POST"])
@login_required
def delete_material():
    """
    Удаляет указанный файл из папки materials/<group>/.
    """
    teacher_only()

    group = request.form.get("group")
    filename = request.form.get("filename")
    if not group or not filename:
        flash("Не указана группа или файл для удаления", "error")
        return redirect(url_for("materials.view_materials"))

    materials_root = os.path.join(current_app.root_path, "materials")
    file_path = os.path.join(materials_root, group, filename)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            flash("Файл удалён", "info")
        except Exception as e:
            flash(f"Ошибка при удалении файла: {str(e)}", "error")
    else:
        flash("Файл не найден", "error")

    return redirect(url_for("materials.view_materials", group=group))


@materials_bp.route("/materials/download/<group>/<filename>")
@login_required
def download_material(group, filename):
    """
    Позволяет скачать файл из папки materials/<group>/.
    Доступны всем авторизованным пользователям.
    """
    materials_root = os.path.join(current_app.root_path, "materials")
    group_dir = os.path.join(materials_root, group)
    if not os.path.exists(os.path.join(group_dir, filename)):
        abort(404)
    return send_from_directory(group_dir, filename, as_attachment=True)
