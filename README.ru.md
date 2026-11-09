# Translate Book Parallel (Параллельный перевод книг)

[English](README.md) | [Русский](README.ru.md)

**Скилл для агента** — переводит целые книги (PDF/DOCX/EPUB) на любой язык, используя параллельные саб-агенты с возобновляемым пайплайном.

Изначально сделан для Hermes Agent. Сам пайплайн не привязан к хосту: он работает в OpenCode, Claude Code, Codex и любом агенте с shell/file-инструментами и саб-агентами — см. [AGENT_ADAPTER.md](AGENT_ADAPTER.md).

> Портирован из [deusyu/translate-book](https://github.com/deusyu/translate-book) (Rainman Translate Book) для Hermes Agent.  
> Оригинал вдохновлён [claude_translater](https://github.com/wizlijun/claude_translater).

---

## Принцип работы

```
Вход (PDF/DOCX/EPUB)
  │
  ▼
Calibre → HTMLZ → Markdown (чанки ~15000 символов)
  │
  ▼
Параллельные саб-агенты (инструмент хоста: delegate_task / subagent / Task)
  │  каждый переводит 1 чанк в изолированном контексте
  ▼
Валидация → Слияние → Сборка
  │
  ▼
HTML / DOCX / EPUB / PDF
```

Каждый чанк получает собственного саб-агента со свежим контекстом. Это предотвращает переполнение контекста и обрезание вывода, типичное для перевода книг в одной сессии.

## Возможности

- **Параллельный перевод** — несколько чанков переводятся одновременно через инструмент саб-агентов хоста
- **Возобновляемость** — уже переведённые чанки автоматически пропускаются при перезапуске
- **Глоссарий** — единая таблица терминов для согласованности между чанками
- **Выборочный ре-перевод** — только чанки, затронутые изменениями в глоссарии
- **Контекст соседей** — каждый чанк видит короткие выдержки из соседних для разрешения местоимений и сущностей
- **Валидация целостности** — SHA-256 хеши предотвращают слияние устаревших/повреждённых данных
- **Мультиформатный вывод** — HTML (плавающее оглавление), DOCX, EPUB, PDF
- **Форматы ввода** — PDF, DOCX, EPUB (обрабатываются Calibre)
- **Языки с отдельными промптами** — zh (китайский), ru (русский), en, ja, ko, fr, de, es

## Требования

| Компонент | Обязательно | Установка |
|-----------|-------------|-----------|
| **Python 3.9+** | Да | `python --version` |
| **Calibre** (ebook-convert) ≥ 9.x | Да | [calibre-ebook.com](https://calibre-ebook.com/) или `winget upgrade calibre.calibre` |
| **Pandoc** | Да | `winget install JohnMacFarlane.Pandoc` |
| **pypandoc** | Да | `pip install pypandoc` |
| **beautifulsoup4** | Рекомендуется | `pip install beautifulsoup4` |

Проверка:

```bash
ebook-convert --version
pandoc --version
python -c "import pypandoc; print('pypandoc ok')"
```

## Установка (Hermes)

```bash
# 1. Клонировать репозиторий
git clone https://github.com/L-MORIA/translate-book-parallel-pro.git

# 2. Установить зависимости
python scripts/setup.py

# 3. Установить скилл в Hermes
cp -r translate-book-parallel-pro "${HERMES_HOME:-$HOME/.hermes}/skills/translate-book-parallel-pro"

# 4. Перезагрузить скиллы
# Выполнить /reload-skills в чате
```

Проверка:

```bash
skill_view(name='translate-book-parallel-pro')
# → readiness_status: available
```

## Использование

После установки скажите Hermes:

```
переведи /path/to/book.epub на русский
```

```
переведи /path/to/book.pdf на китайский параллельными саб-агентами
```

### Ручной запуск этапов пайплайна

```bash
# 1. Конвертация в чанки
python scripts/convert.py /path/to/book.pdf --olang ru

# 2. Создание глоссария (опционально, для согласованности терминов)
# (выполняется скиллом автоматически)

# 3. Перевод — выполняется скиллом через delegate_task

# 4. Слияние и сборка форматов
python scripts/merge_and_build.py --temp-dir book_temp --title "Название книги"
```

Результаты в `book_temp/`:

| Файл | Формат |
|------|--------|
| `output.md` | Слитый переведённый Markdown |
| `book.html` | Веб-версия с плавающим оглавлением |
| `book_doc.html` | Ebook HTML |
| `book.docx` | Документ Word |
| `book.epub` | Электронная книга EPUB |
| `book.pdf` | PDF (для печати) |

## Поддерживаемые языки

| Код | Язык |
|------|------|
| `zh` | Китайский |
| `en` | Английский |
| `ja` | Японский |
| `ko` | Корейский |
| `ru` | Русский |
| `fr` | Французский |
| `de` | Немецкий |
| `es` | Испанский |

Коды языков расширяемые — добавьте новые в триггеры скилла в `SKILL.md`.

## Архитектура

См. [ARCHITECTURE.md](ARCHITECTURE.md) — диаграмма пайплайна и описание компонентов.

## План развития

См. [ROADMAP.md](ROADMAP.md). Главное направление — MCP-сервер, чтобы один и
тот же пайплайн работал в OpenCode, Claude Code, Codex, ZCode, MiniMax Code,
Kimi и любом MCP-совместимом агенте. Headless-оркестратор и устанавливаемые
адаптеры под хосты — промежуточные шаги.

**MVP MCP-сервера реализован (v1.3.0)** — stdio, JSON-RPC на чистом stdlib,
без SDK-зависимости. Упрочнение транспорта, шаблоны ресурсов и живая проверка
в OpenCode V2 вошли в v1.3.3:

```bash
python scripts/mcp_server.py --workspace /путь/к/книгам
```

Инструменты: `convert_book`, `get_status`, `get_translation_plan`,
`get_chunk_prompt`, `submit_translation`, `merge_meta`, `validate_book`,
`build_book`. Сервер сам не вызывает LLM — хост-агент переводит промпты,
которые тот возвращает (сам или через своих суб-агентов). Осталось:
упаковка (M4) и HTTP-транспорт (M5).

## Известные проблемы

- **Память:** При concurrency >1 на системах с 8GB RAM возможно переполнение памяти.
  Решение: используйте `concurrency: 1` в конфигурации перевода.
  См. `scripts/setup.py` — проверка RAM встроена в установку.

## Что изменено относительно оригинала

См. [CHANGELOG.md](CHANGELOG.md) — полный список адаптаций под Hermes.

## Лицензия

MIT — как и оригинальный [deusyu/translate-book](https://github.com/deusyu/translate-book).
