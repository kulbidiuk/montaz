# Telegram → Obsidian: захват мыслей в инбокс + разбор через Claude

Связка «второго мозга» из двух гайдов:

1. **Захват** — диктуешь/пишешь мысль боту в Telegram → она падает в `inbox.md` твоего
   Obsidian-хранилища.
2. **Разбор** — Claude по правилам из `CLAUDE.md` раскладывает мысли по заметкам и
   проектам, вытаскивает задачи и каждое утро отдаёт приоритеты дня.

В этой папке — две реализации захвата (на выбор) и готовый каркас хранилища для разбора.

```
telegram-obsidian/
├── bot.py                 # self-hosted бот: Telegram -> inbox.md (без плагина, работает 24/7)
├── config.example.json    # пример конфига (скопируй в config.json)
├── test_bot.py            # офлайн-тесты логики (без сети):  python3 test_bot.py
├── examples/
│   ├── tg-obsidian-bot.service  # systemd-юнит для всегда-включённого бота
│   └── triage.crontab           # cron для авто-разбора через Claude Code
└── vault-template/        # каркас Second Brain — копируется в твой Obsidian-vault
    ├── CLAUDE.md          # правила разбора инбокса (Гайд 2)
    └── _BRAIN/
        ├── Инбокс/{inbox.md, _processed.md, attachments/}
        ├── Заметки/  Решения/  Дайджесты/
        ├── PROJECTS.md  Приоритеты.md  STACK.md
```

---

## Часть 1. Захват (Гайд 1)

Есть два пути. Выбери один.

### Путь A — плагин Obsidian (просто, но нужен открытый Obsidian)

Это исходный способ из гайда. Кода не нужно, но мысли подтягиваются, только пока
открыт Obsidian.

1. В Telegram открой **@BotFather** → `/newbot` → задай имя и юзернейм (заканчивается
   на `bot`). Скопируй **токен** (`12345678:AAE…`) — это ключ, никому не показывай.
2. Obsidian → **Настройки → Community plugins → Browse** → найди **Telegram Sync**
   (автор *soberhacker*) → Install → Enable.
3. Открой настройки плагина → вставь **Bot token** → подтверди подключение
   (статус «Connected»). Напиши боту любое сообщение — проверь, что оно пришло.
4. Настрой складывание в один файл:
   - **New notes location** → папка `_BRAIN/Инбокс`.
   - **Append to existing note** (дописывать в один файл) → включи, файл `inbox.md`.
   - **Template**:
     ```
     ## {{messageTime:YYYY-MM-DD HH:mm}} · telegram
     {{content}}{{voiceTranscript}}
     ---
     ```
   - Есть Telegram **Premium** → включи **Voice transcript** (голос приходит текстом).
5. Сохрани и проверь: запиши боту голос/текст → открой `_BRAIN/Инбокс/inbox.md` →
   появился блок с датой и мыслью.

Плагин: <https://github.com/soberhacker/obsidian-telegram-sync>

### Путь B — self-hosted бот `bot.py` (работает 24/7, даже когда Obsidian закрыт)

Реализация «всегда-включённого компьютера» из раздела гайда «важные мелочи». Тот же
результат (мысли падают в `inbox.md` с тем же шаблоном), но не зависит от открытого
Obsidian и не требует Premium для голоса.

Требования: **Python 3.9+**, никаких зависимостей (только стандартная библиотека).

1. Создай бота у **@BotFather** и скопируй токен (как в Пути A, шаг 1).
2. Настрой конфиг:
   ```bash
   cd telegram-obsidian
   cp config.example.json config.json
   ```
   В `config.json` укажи:
   - `bot_token` — токен от BotFather (или задай переменную окружения `TG_BOT_TOKEN`);
   - `vault_path` — путь к твоему Obsidian-хранилищу (или `OBSIDIAN_VAULT`);
   - при желании `timezone` (напр. `Europe/Moscow`) и `allowed_user_ids`.
3. Запусти:
   ```bash
   python3 bot.py
   ```
4. Напиши боту `/id` — он ответит твоим Telegram user id. Впиши его в
   `allowed_user_ids: [123456789]`, чтобы бот принимал только тебя, и перезапусти.
5. Проверь: напиши боту «идея для контента…» → бот ответит `✓ в инбоксе` →
   мысль появилась в `_BRAIN/Инбокс/inbox.md`.

Каждый блок выглядит так (шаблон из гайда):

```
## 2026-06-27 09:05 · telegram
идея для контента: снять видео про то, как я веду заметки

---
```

**Голосовые.** Telegram отдаёт ботам только аудио-файл (авто-расшифровка Premium —
функция клиента, не API). Поэтому по умолчанию голос скачивается в
`attachments/` и встраивается в инбокс как `![[voice_….ogg]]`. Хочешь текст —
включи расшифровку своим инструментом:

```json
"voice": { "save": true, "transcribe": true, "transcribe_cmd": "whisper {file} --model small --output_format txt --output_dir /tmp && cat /tmp/$(basename {file} .ogg).txt" }
```

`{file}` подставляется путём к аудио, расшифровка читается из stdout команды. Если
команда упадёт — аудио всё равно сохранится (мысль не теряется).

**Всегда включённым** бот делается через systemd — см.
[`examples/tg-obsidian-bot.service`](examples/tg-obsidian-bot.service).

Не коннектится из дома? Если Telegram блокируется провайдером — включи VPN, боту
нужен доступ к `api.telegram.org`.

---

## Часть 2. Разбор через Claude (Гайд 2)

1. Скопируй содержимое `vault-template/` в корень своего Obsidian-хранилища
   (`CLAUDE.md` — в корень, папку `_BRAIN/` — рядом). Если каркас Second Brain уже
   стоит — просто перенеси блок «Разбор инбокса» из `CLAUDE.md` в свой `CLAUDE.md`.
2. Запусти Claude Code в папке хранилища — он автоматически прочитает `CLAUDE.md`.
3. **Вручную:** напиши `разбери инбокс`. Claude пройдёт по новым блокам, разложит их
   по заметкам/проектам/решениям, вырежет разобранное в `_processed.md` и выдаст отчёт
   «что куда ушло».
4. **Автоматически:** настрой расписание из
   [`examples/triage.crontab`](examples/triage.crontab) — лёгкий разбор в 09:00/13:00/19:00
   и полный утренний дайджест в 07:00 (сводка дня в `_BRAIN/Дайджесты/ДАТА.md`).

Правила разбора, таблица маршрутизации и формула приоритизации
(`Скор = Деньги×2 + Рычаг + Обязательство − Операционка`) — внутри
[`vault-template/CLAUDE.md`](vault-template/CLAUDE.md).

---

## Тесты

```bash
cd telegram-obsidian
python3 test_bot.py        # офлайн, без токена и сети
```

## Безопасность

- `config.json` и `state.json` в `.gitignore` — токен и состояние не попадают в git.
- Реальные секреты держи в `STACK.md` локально (или в менеджере паролей), не коммить.
- Токен бота — это полный доступ к боту: никому не передавай.

## Источники

Гайды: захват (Telegram → Obsidian) и разбор инбокса через Claude.
Плагин Telegram Sync — <https://github.com/soberhacker/obsidian-telegram-sync>.
