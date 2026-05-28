# Claude Code: подключённые плагины/навыки

Этот репозиторий настроен так, чтобы в любой сессии Claude Code (включая
[Claude Code на вебе](https://code.claude.com/docs/en/claude-code-on-the-web))
автоматически подключались два проверенных набора навыков. Конфигурация
лежит в [`settings.json`](./settings.json) — ключи `extraKnownMarketplaces`
и `enabledPlugins`.

При первом открытии репозитория Claude Code покажет диалог доверия
(trust prompt) для загрузки marketplace и плагинов — это ожидаемо.

## Подключённые плагины

| Плагин | Источник | Что делает |
|--------|----------|------------|
| **Superpowers** | [`obra/superpowers-marketplace`](https://github.com/obra/superpowers-marketplace) | Фреймворк навыков и методология разработки: TDD, отладка, `/brainstorm`, `/write-plan`, `/execute-plan` |
| **GSD** (Get Shit Done) | [`jnuyens/gsd-plugin`](https://github.com/jnuyens/gsd-plugin) — нативная упаковка [`gsd-build/get-shit-done`](https://github.com/gsd-build/get-shit-done) (автор TÂCHES) | Трёхфазный поток Plan → Execute → Verify со spec-driven разработкой; команды `/gsd:*` |

## Ручная установка (альтернатива)

Если хочешь установить в свой **локальный** Claude Code вручную, выполни в сессии:

```
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace

/plugin marketplace add jnuyens/gsd-plugin
/plugin install gsd@gsd-plugin
```

## Заметки о проверке фактов

В исходном сообщении, по которому собирали этот список, были ошибки:

- **Звёзды завышены/выдуманы** (149K / 51K) — у реальных репозиториев на
  порядки меньше.
- **GSD**: автор — не «Lex Christopherson», а **TÂCHES**; репозитория
  `lexchristopherson/gsd` не существует. Используется официальный
  `gsd-build/get-shit-done` и его плагин-упаковка `jnuyens/gsd-plugin`.
- **Clawd** (`dcodesdev/clawd`) — реальный, но это отдельный Rust-CLI
  менеджер навыков, а не сам навык. Установка `curl -fsSL
  https://api.clawd.xyz/install.sh | sh` — на твоё усмотрение; здесь она
  намеренно не выполнялась (установка стороннего бинарника пайпом из shell).
