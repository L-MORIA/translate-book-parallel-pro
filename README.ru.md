# Translate Book Parallel (Параллельный перевод книг)

[English](README.md) | [Русский](README.ru.md)

**Скилл для Hermes Agent** — переводит целые книги (PDF/DOCX/EPUB) на любой язык, используя параллельные саб-агенты с возобновляемым пайплайном.

> Портирован из [deusyu/translate-book](https://github.com/deusyu/translate-book) (Rainman Translate Book) для Hermes Agent.  
> Оригинал вдохновлён [claude_translater](https://github.com/wizlijun/claude_translater).

---

## Принцип работы

```
Вход (PDF/DOCX/EPUB)
  │
  ▼
Calibre → HTMLZ → Markdown (чанки ~6000 символов)
  │
  ▼
Параллельные саб-агенты (Hermes delegate_task)
  │  каждый переводит 1 чанк в изолированном контексте
  ▼
Валидация → Слияние → Сборка
  │
  ▼
HTML / DOCX / EPUB / PDF
```

Каждый чанк получает собственного саб-агента со свежим контекстом. Это предотвращает переполнение контекста и обрезание вывода, типичное для перевода книг в одной сессии.

## Возможности

- **Параллельный перевод** — несколько чанков переводятся одновременно через `delegate_task`
- **Возобновляемость** — уже переведённые чанки автоматически пропускаются при перезапуске
- **Глоссарий** — единая таблица терминов для согласованности между чанками
- **Выборочный ре-перевод** — только чанки, затронутые изменениями в глоссарии
- **Контекст соседей** — каждый чанк видит короткие выдержки из соседних для разрешения местоимений и сущностей
- **Валидация целостности** — SHA-256 хеши предотвращают слияние устаревших/повреждённых данных
- **Мультиформатный вывод** — HTML (плавающее оглавление), DOCX, EPUB, PDF
- **Форматы ввода** — PDF, DOCX, EPUB (обрабатываются Calibre)
- **Языки** — zh, en, ja, ko, fr, de, es (расширяемые)

## Требования

| Компонент | Обязательно | Установка |
|-----------|-------------|-----------|
| **Python 3.8+** | Да | `python --version` |
| **Calibre** (ebook-convert) | Да | [calibre-ebook.com](https://calibre-ebook.com/) |
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
git clone https://github.com/L-MORIA/translate-book-parallel.git
cp -r translate-book-parallel "${HERMES_HOME:-$HOME/.hermes}/skills/translate-book-parallel"

# 2. Перезагрузить скиллы
# Выполнить /reload-skills в чате
```

Проверка:

```bash
skill_view(name='translate-book-parallel')
# → readiness_status: available
```

## Использование

После установки скажите Hermes:

```
переведи D:\books\clean-code.epub на русский
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
| `fr` | Французский |
| `de` | Немецкий |
| `es` | Испанский |

Коды языков расширяемые — добавьте новые в триггеры скилла в `SKILL.md`.

## Архитектура

См. [ARCHITECTURE.md](ARCHITECTURE.md) — диаграмма пайплайна и описание компонентов.

## Что изменено относительно оригинала

См. [CHANGELOG.md](CHANGELOG.md) — полный список адаптаций под Hermes.

## Лицензия

MIT — как и оригинальный [deusyu/translate-book](https://github.com/deusyu/translate-book).
