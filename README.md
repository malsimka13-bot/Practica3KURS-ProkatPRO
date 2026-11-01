# ПрокатПро — веб-приложение «Прокат оборудования»

Бронирование спортивного, туристического и строительного оборудования: каталог с фото и фильтрами, три роли (клиент, менеджер, администратор), проверка пересечения дат, склад со списанием, автоматические штрафы, статистика.
Стек: Python, FastAPI, SQLAlchemy, SQLite, HTML/CSS/JavaScript.

> **Проверяющим.** Сайт запускается локально. Выберите инструкцию для своей операционной системы и выполняйте команды по порядку. В Windows и Linux они отличаются, смешивать их нельзя.

## Запуск в Windows

1. Установите Python 3.11 или новее с python.org. В установщике отметьте «Add python.exe to PATH».
2. Скачайте проект ZIP-архивом, распакуйте и откройте папку проекта.
3. Нажмите правой кнопкой в пустом месте папки и выберите «Открыть в терминале».
4. Выполните по очереди:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app
```

Если PowerShell запрещает активацию, выполните `Set-ExecutionPolicy -Scope Process Bypass` и повторите вторую команду. Если команда `python` не найдена, используйте `py`.

5. Откройте в браузере http://127.0.0.1:8000. Остановить сервер: Ctrl+C.

## Запуск в Linux и macOS

1. Установите Python 3.11 или новее и модуль venv:
   - Ubuntu/Debian: `sudo apt install python3 python3-venv python3-pip`
   - Arch: `sudo pacman -S python`
   - Fedora: `sudo dnf install python3`
2. Скачайте проект, распакуйте и перейдите в его папку командой `cd`.
3. Выполните по очереди:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app
```

Окружение `.venv` обязательно: в Arch и новых Ubuntu `pip` не ставит пакеты в систему.

4. Откройте в браузере http://127.0.0.1:8000. Остановить сервер: Ctrl+C.

## Если что-то не работает

- Порт 8000 занят: добавьте к последней команде `--port 8001` и откройте соответствующий адрес.
- Нужны чистые данные: остановите сервер (Ctrl+C), удалите файл `rental.db` и запустите снова. Файл удаляют только при остановленном сервере.
- Фото не отображаются: проверьте, что картинки лежат в `static/img/` (velosiped.jpg, snowboard.jpg, samokat.jpg, palatka.jpg, spalnik.jpg, ryukzak.jpg, perforator.jpg, shlifmashina.jpg, lesa.jpg).

## Демо-аккаунты

| Роль | Email | Пароль |
|---|---|---|
| Администратор | admin@rent.local | admin123 |
| Менеджер | manager@rent.local | manager123 |
| Клиент | client@rent.local | client123 |

## Тесты

С активированным окружением: `pytest -q` (28 автотестов на временной базе). Коллекция Postman: `postman/prokat-pro.postman_collection.json` (Import, затем Runner).

## Структура

| Путь | Назначение |
|---|---|
| `app/main.py` | API, роли, JWT |
| `app/services.py` | бизнес-правила: доступность, статусы, штрафы |
| `app/models.py` | таблицы БД |
| `static/index.html` | клиентская часть |
| `static/img/` | фото оборудования |
| `tests/` | автотесты |
| `postman/` | коллекция запросов |
