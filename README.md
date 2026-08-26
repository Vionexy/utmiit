# schedule bot

бот для расписания колледжа, разбил на файлы чтобы было проще ковыряться

## структура

- `config.py` — токены, константы, расписание файлов
- `db.py` — работа с sqlite
- `cache_store.py` — кэш отрендеренных страниц
- `state_store.py` — состояния (когда бот ждёт от юзера ввод)
- `schedule_service.py` — скачать pdf, сделать png
- `github_publish.py` — заливка на гитхаб
- `broadcast.py` — рассылка подписчикам
- `media.py` — отправка страниц альбомом
- `keyboards.py` — кнопки и подписи к сообщениям
- `middleware.py` — антифлуд и трекинг юзеров
- `app_context.py` — тут живут bot, db и всё остальное одним объектом
- `handlers_commands.py` / `handlers_callbacks.py` / `handlers_payments.py` — хендлеры
- `check_loop.py` — фоновая проверка расписания каждые 15 мин
- `main.py` — запуск

## как запустить

```bash
pip install -r requirements.txt
cp .env.example .env
# вписать туда BOT_TOKEN и ADMIN_ID
python main.py
```

.env подхватывается сам, экспортировать вручную не надо.

GITHUB_TOKEN можно не заполнять, если публикация на гитхаб не нужна.

## переменные окружения

обязательные: `BOT_TOKEN`, `ADMIN_ID`.

остальные с дефолтами:

- `DB_PATH` — файл базы, по умолчанию `subscribers.db`
- `TZ_OFFSET_HOURS` — смещение таймзоны, по умолчанию 7
- `LOG_LEVEL` — по умолчанию INFO
- `LOG_FILE` — файл логов с ротацией, по умолчанию `bot.log`, пустая строка отключает
- `GITHUB_BRANCH`, `GITHUB_SITE_PATH` — куда публиковать, по умолчанию `main` и `schedule`

## тесты

```bash
pip install -r requirements-dev.txt
python -m pytest
```

