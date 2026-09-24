"""Функции работы с локальным пулом пользователей банка.

Пул хранится в файле ``data/users.json`` (относительно корня проекта)
в формате JSON-объекта с массивом пользователей: {"users": [...]}.

Модуль предоставляет:
    - load_users()                 — чтение справочника;
    - save_users(users)            — атомарная запись справочника;
    - generate_one_user(...)       — создание одной записи пользователя;
    - generate_users(count)        — добавление новых пользователей в пул;
    - deactivate_users(count)      — деактивация случайных активных пользователей;
    - activate_users(count)        — активация случайных неактивных пользователей.

Внешние зависимости: только Faker и стандартная библиотека.
"""

from __future__ import annotations

import json
import os
import random
from datetime import date, timedelta

from faker import Faker

# --- Константы -------------------------------------------------------------

MIN_USERS = 250  # ниже этого порога deactivate_users не работает
MAX_USERS = 3000  # выше этого порога generate_users не работает

# Путь к файлу пула — относительно корня проекта (каталога, где лежит модуль).
_PROJECT_ROOT = os.getcwd()
USERS_FILE = os.path.join(_PROJECT_ROOT, "data", "users.json")

_fake = Faker("ru_RU")


# --- Вспомогательные функции -----------------------------------------------


def load_users() -> list[dict]:
    """Читает ``data/users.json`` и возвращает список пользователей.

    Если файл отсутствует или пуст (например, был создан случайно через
    перенаправление) — возвращает пустой список.
    Если файл повреждён (невалидный JSON) — возбуждает исключение
    с понятным сообщением.
    """
    if not os.path.exists(USERS_FILE):
        return []
    if os.path.getsize(USERS_FILE) == 0:
        # Пустой файл считаем отсутствующим справочником, а не повреждённым.
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Файл пользователей {USERS_FILE} повреждён: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        raise ValueError(
            f"Файл пользователей {USERS_FILE} имеет неверную структуру: "
            'ожидался JSON-объект вида {{"users": [...]}}'
        )
    return data["users"]


def save_users(users: list[dict]) -> None:
    """Сохраняет список пользователей в ``data/users.json``.

    Запись атомарная: сначала временный файл ``data/users.json.tmp``,
    затем переименование поверх целевого файла.
    """
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    tmp_path = USERS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, USERS_FILE)


def _random_past_date() -> date:
    """Случайная дата в прошлом (за последний год)."""
    return date.today() - timedelta(days=random.randint(1, 365))


def generate_one_user(
    register_date: date | str,
    user_id: int,
) -> dict:
    """Создаёт одну запись пользователя по правилам генерации полей.

    :param register_date: дата регистрации (date или ISO-строка);
    :param user_id: уникальный ID пользователя.
    """
    if isinstance(register_date, str):
        reg_date = date.fromisoformat(register_date)
    else:
        reg_date = register_date

    # Дата рождения: случайная дата в диапазоне от 18 до 80 лет
    # относительно register_date.
    age_days = random.randint(18 * 365, 80 * 365)
    birth_date = reg_date - timedelta(days=age_days)

    passport_number = f"{_fake.numerify('####')} {_fake.numerify('######')}"
    account_number = _fake.numerify("#" * 20)

    return {
        "user_id": user_id,
        "fio": _fake.name(),
        "birth_date": birth_date.isoformat(),
        "city": _fake.city_name(),
        "phone": _fake.phone_number(),
        "email": _fake.email(),
        "register_date": reg_date.isoformat(),
        "passport_number": passport_number,
        "address": _fake.address().replace("\n", ", "),
        "account_number": account_number,
        "is_active": True,
    }


def _next_user_id(users: list[dict]) -> int:
    """Возвращает ID для нового пользователя: max(user_id) + 1 либо 1."""
    if not users:
        return 1
    return max(u["user_id"] for u in users) + 1


# --- Основные функции --------------------------------------------------------


def generate_users(count: int) -> int:
    """Создаёт ``count`` новых пользователей и добавляет их к существующему пулу.

    Возвращает количество фактически добавленных пользователей.
    При ``count <= 0`` возбуждает ``ValueError``.
    Если пул уже на пределе ``MAX_USERS`` — возвращает 0.
    """
    if count <= 0:
        raise ValueError(f"count должен быть положительным, получено: {count}")

    users = load_users()

    if len(users) >= MAX_USERS:
        return 0

    actual_count = min(count, MAX_USERS - len(users))

    for _ in range(actual_count):
        new_user = generate_one_user(
            register_date=date.today(),
            user_id=_next_user_id(users),
        )
        users.append(new_user)

    save_users(users)
    return actual_count


def deactivate_users(count: int) -> int:
    """Деактивирует ``count`` случайных активных пользователей.

    Возвращает количество фактически деактивированных пользователей.
    При ``count <= 0`` возбуждает ``ValueError``.
    Если размер пула ниже ``MIN_USERS`` — возвращает 0 и ничего не делает.
    """
    if count <= 0:
        raise ValueError(f"count должен быть положительным, получено: {count}")

    users = load_users()

    if len(users) < MIN_USERS:
        return 0

    active = [u for u in users if u.get("is_active")]
    if not active:
        return 0

    to_deactivate = min(count, len(active))
    chosen = random.sample(active, to_deactivate)
    for u in chosen:
        u["is_active"] = False

    save_users(users)
    return to_deactivate


def activate_users(count: int) -> int:
    """Активирует ``count`` случайных неактивных пользователей.

    Возвращает количество фактически активированных пользователей.
    При ``count <= 0`` возбуждает ``ValueError``.
    Лимитами не ограничен.
    """
    if count <= 0:
        raise ValueError(f"count должен быть положительным, получено: {count}")

    users = load_users()

    inactive = [u for u in users if not u.get("is_active")]
    if not inactive:
        return 0

    to_activate = min(count, len(inactive))
    chosen = random.sample(inactive, to_activate)
    for u in chosen:
        u["is_active"] = True

    save_users(users)
    return to_activate
