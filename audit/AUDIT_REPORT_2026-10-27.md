# Аудит проекта `translate-book-parallel-pro`

| | |
|---|---|
| **Репозиторий** | `F:\translate-book-parallel-pro` (`L-MORIA/translate-book-parallel-pro`) |
| **Дата аудита** | 2026-10-27 |
| **Локальная ревизия** | `cde660b` (ветка `master`) |
| **Ревизия на remote** | `8a1606a` — *v1.2.1: full audit — security & correctness fixes, +45 tests, CI integration gate, repo hygiene* (2026-10-25) |
| **Метод** | чтение всех 55 отслеживаемых файлов + прогон юнит-тестов + статический анализ (ruff/pyflakes/`ast` 3.9) + 10 ограниченных поведенческих проб в `%TEMP%` (без записи в репозиторий) |
| **Тесты** | локально `cde660b`: **226 OK**; дерево `8a1606a`: **271 OK** (Python 3.14.3) |
| **Секреты** | не найдено (55 файлов, 0 токенов/ключей/адресов) |

> **Важно:** локальная копия отстаёт от remote на один коммит. 22 из найденных проблем уже исправлены в v1.2.1. Отчёт разделён на «открыто сейчас» (§2–§5) и «уже исправлено, повторно не чинить» (§6).

> **Статус на 2026-10-27/28 (после аудита):** C-01, C-02, C-05 исправлены в v1.2.2 (`fbff215`), C-03 — в v1.2.3, C-04 — в v1.2.4, C-06 — в v1.2.5. Тексты разделов ниже описывают состояние **на момент аудита** и не переписывались. Открыто 12 из 18 пунктов: C-07…C-12, D-01…D-04, T-01, T-02.

---

## 0. Мета-наблюдение: аудит делается не по той ревизии

```
LOCAL  = cde660b   (2026-08-03)
REMOTE = 8a1606a   (2026-10-25)  ← origin/master, 1 коммит впереди
git status → clean, ветка master, локальных коммитов нет
```

Практические следствия:

1. Все баги из этого отчёта, помеченные «локально», видны в `F:\translate-book-parallel-pro`, но часть из них в v1.2.1 уже закрыта.
2. Один баг (`C-04`, обход санитайзера) существует **только** в v1.2.1 — его в локальной копии нет, потому что там нет и самого санитайзера.
3. Рекомендация: `git pull --ff-only origin master` (дерево чистое, терять нечего), затем исправлять только §2–§5. Повторное «исправление» уже закрытых пунктов даст конфликты.

---

## 1. Сводка

| ID | Severity | Область | Проблема | Есть в `cde660b` | Есть в `8a1606a` |
|---|---|---|---|---|---|
| **C-01** | 🔴 critical | `convert.py` | Частичный набор чанков молча принимается → книга собирается неполной | да | **да** |
| **C-02** | 🔴 critical | `_mab_html.py` | `book.html` не перегенерируется; `--title/--author/--lang` игнорируются при повторном запуске | да | **да** |
| **C-03** | 🟠 high | `convert.py` | Любой заголовок принудительно режет чанк → `--chunk-size` работает только как потолок | да | **да** |
| **C-04** | 🟠 high (security) | `_mab_html.py` | Обход `sanitize_html_body`: безкавычные `on*=`, `<iframe src="javascript:">`, `formaction=` | нет | **да** |
| **C-05** | 🟠 high | `manifest.py` | Битый/неполный `manifest.json` → `JSONDecodeError` / `KeyError` трейсбеком; запись неатомарная | да | **да** |
| **C-06** | 🟠 high | `SKILL.md` | «Correct example» байт-в-байт равен «wrong example»; в русский промпт вклеены китайские слова | да | **да** |
| **C-07** | 🟡 medium | `merge_meta.py` | `prepare-merge`/`apply-merge` падают трейсбеком, если нет `glossary.json` | да | **да** |
| **C-08** | 🟡 medium | `_mab_formats.py` | `generate_formats()` возвращает `None` вместо `False` | да | **да** |
| **C-09** | 🟡 medium | `merge_and_build.py` | `--cleanup` необратим: после него пересборка невозможна без повторного перевода | да | **да** |
| **C-10** | 🟡 medium | `translate-launcher.bat` | Обещает `.txt` (конвертер его отвергает), `--title` = имя файла, голый `pip`, «v1.0» | да | **да** |
| **C-11** | 🟡 low | `create-desktop-shortcut.ps1` | `` `u{2705} `` печатается буквально в Windows PowerShell 5.1 | да | **да** |
| **C-12** | 🟡 low | `convert.py` | Дефолты `target_size=6000` в сигнатурах против CLI-дефолта 15000 | да | **да** |
| **D-01** | 🟡 medium | `ARCHITECTURE.md` | «~6000 chars», «five output formats» (перечислено четыре) | да | **да** |
| **D-02** | 🟡 low | `README*.md` | «~6000-char chunks» в трёх README | да | **да** |
| **D-03** | 🟡 medium | `tests/baselines/*` | Метрики зафиксированы под `target_size=6000`/concurrency 8 → невоспроизводимы | да | **да** |
| **D-04** | 🟡 low | `SKILL.md` | Куда попадают файлы (стр. 501) и противоречие про concurrency 24/3 | да | **да** |
| **T-01** | 🟡 medium | `tests/` | 72 из 129 функций не упоминаются в тестах; непокрыт именно код из C-01/C-05/C-09 | да | **да** (72/129) |
| **T-02** | 🟡 low | `.github/workflows/ci.yml` | Зависимости не запинены, `cache-dependency-path` указывает на файл без зависимостей, нет линт-гейта | да | **да** |
| **S-01** | ✅ | весь репозиторий | Секретов, приватных IP, `shell=True`, `eval/exec/pickle` нет | — | — |

Итого открыто: **2 критических, 4 высоких, 12 средних/низких** (18 пунктов). Ещё 15 классов проблем уже закрыты в v1.2.1 — их переделывать не нужно (см. §6).

---

## 2. Критические

### C-01 🔴 Тихая потеря чанков: неполный temp-каталог принимается за готовый

**Где:** `scripts/convert.py:757` (`_do_split_and_manifest`), `scripts/convert.py:718` (`_find_existing_chunk_files`)

```python
existing = _find_existing_chunk_files(temp_dir)
if existing:
    print(f"Skipping markdown splitting - found {len(existing)} existing chunk files")
    create_manifest(temp_dir, existing, input_md)   # манифест переписывается под то, что осталось
    return len(existing)
```

Проверяется только факт «есть хотя бы один `chunk*.md`». Ни непрерывность нумерации, ни суммарный размер против `input.md`, ни соответствие манифесту не сверяются. Манифест затем **перегенерируется** по фактическому содержимому каталога, то есть сам себя «легитимизирует».

**Доказано пробой** (3 чанка → удалены 2 и `manifest.json` → повторный запуск):

```
Split into 3 chunks
  chunk0001.md: 2017 characters
  chunk0002.md: 2017 characters
  chunk0003.md: 2015 characters
Created manifest.json (3 chunks)
Skipping markdown splitting - found 1 existing chunk files
Created manifest.json (1 chunks)
[A] VERDICT: BUG - lost 2 chunks silently
```

**Как это стреляет в жизни:** прерывание по Ctrl+C посреди нарезки, заполнение диска, блокировка файла антивирусом, ручное удаление «подозрительного» чанка, оборванный `os.remove` при очистке. После этого:

- `manifest.json` содержит `chunk_count: 1` и `source_hash` **всего** `input.md` — то есть гейт целостности доволен;
- `merge_and_build` валидирует manifest против реальности, ошибок не находит;
- книга собирается из 1 чанка, остальные 95 % текста отсутствуют;
- **exit code 0**, в логах ни одного слова о проблеме.

Это единственная найденная проблема, приводящая к тихой порче результата (не к падению), поэтому — critical.

**Как починить (эскиз):**

```python
existing = _find_existing_chunk_files(temp_dir)
if existing:
    numbers = sorted(int(re.search(r'chunk(\d+)', f).group(1)) for f in existing)
    total = sum(os.path.getsize(os.path.join(temp_dir, f)) for f in existing)
    expected = os.path.getsize(input_md)
    contiguous = numbers == list(range(1, len(numbers) + 1))
    size_ok = 0.9 * expected <= total <= 1.1 * expected
    if not (contiguous and size_ok):
        print(f"Error: partial chunk set ({len(existing)} files, {total} bytes of {expected}) "
              f"— refusing to reuse. Delete {temp_dir}/chunk*.md or pass --resplit.")
        return 0
```

Плюс тест: набор чанков с дыркой и набор с усечённым последним файлом должны давать отказ.

---

### C-02 🔴 `book.html` не пересобирается, а `--title / --author / --lang` молча игнорируются

**Где:** `scripts/_mab_html.py:240–257` (ранний выход), `:299` (собственно генерация `book.html`)

```python
book_doc_file = os.path.join(temp_dir, 'book_doc.html')
if os.path.exists(book_doc_file):
    if os.path.getmtime(book_doc_file) > os.path.getmtime(md_file):
        if _check_generated_html_sanity(book_doc_file):
            print("Skipping HTML generation - book_doc.html is up to date")
            return True          # ← book.html ещё не создан
```

`book.html` (веб-версия с боковым оглавлением) создаётся **после** этой точки. Проверка смотрит только на `book_doc.html` (ebook-версию) и только на mtime `output.md`.

**Доказано пробой** (`book_doc.html` новее `output.md`, вызов с новым заголовком):

```
Skipping HTML generation - book_doc.html is up to date
[B] convert_md_to_html returned True; book.html exists=False
[B] VERDICT: BUG - web HTML skipped entirely, TOC step will warn and produce nothing
```

**Последствия:**

1. `book.html` отсутствует или остаётся **старым**, а `add_toc` (`_mab_toc.py:184`) в этом случае печатает `Warning: book.html not found, skipping TOC` и продолжает. Форматы (DOCX/EPUB/PDF) собираются из `book_doc.html`, поэтому сборка «успешна», а HTML-результата либо нет, либо он от предыдущей версии.
2. **Смена `--title`, `--author`, `--lang` или `--cover` не даёт эффекта**, если `output.md` не менялся. Пользователь правит опечатку в названии книги, запускает сборку, видит `Build Complete` и получает файлы со старым названием. То же с `--lang` (влияет на `lang`-атрибут и шрифты) и с правкой шаблонов `scripts/template*.html`.
3. То же самое в `_mab_formats.generate_format` (`:30–51`): формат-файлы пропускаются по mtime `book_doc.html` + изображений + обложки, метаданные в ключ не входят.

**Как починить:** хранить рядом `<temp_dir>/.html_stamp.json` с хешем/временем `output.md`, `title`, `author`, `lang_attr` и mtime обоих шаблонов; пропускать генерацию только при полном совпадении штампа **и** наличии обоих файлов (`book_doc.html` и `book.html`). Как минимум — добавить `and os.path.exists(book.html)` в условие пропуска.

---

## 3. Высокие

### C-03 🟠 `--chunk-size` работает только как потолок: заголовок режет чанк всегда

**Где:** `scripts/convert.py:603`

```python
if btype == 'heading' and current_size > 0:
    flush()
```

Докстринг обещает «prefers to split at heading boundaries» (мягкое предпочтение), код реализует жёсткое правило: **каждый** заголовок закрывает текущий чанк. Нижней границы нет.

**Доказано пробой** (10 разделов по ~520 символов, `target_size=15000`):

```
[C] 10 sections x ~520 chars, target_size=15000 -> 10 chunks, sizes=[513, 513, ..., 514]
[C] VERDICT: BUG - chunk-size arg acts as cap only
```

**Последствия:**

- В книгах с плотной рубрикацией (нон-фикшн с `###` на каждом абзаце, поэзия, диалоги с разделителями сцен) число чанков ≈ числу заголовков. При `--chunk-size 15000` пользователь получает в 10–30 раз больше субагентов, чем ожидал, — прямое умножение времени и стоимости.
- Обратная сторона — качество: чанк на 500 символов даёт субагенту почти нулевой контекст, страдает связность перевода и разрешение местоимений (ровно то, ради чего в проекте есть `chunk_context.py`).

**Как починить:** мягкий порог — резать по заголовку только если чанк уже наполовину полон:

```python
if btype == 'heading' and current_size >= target_size * 0.5:
```

и добавить тест «10 коротких разделов при target_size=15000 дают 1 чанк».

---

### C-04 🟠 Санитайзер HTML обходится (только в v1.2.1)

**Где:** `sanitize_html_body()` в `scripts/_mab_html.py` (появился в `8a1606a`)

Функция построена на денилисте регулярок и обрабатывает только значения в кавычках, только `<a href>` и только `<script>`. Проверено на реальном коде из `8a1606a`:

| Payload | Результат |
|---|---|
| `<p>a</p><script>alert(1)</script>` | ✅ вырезано |
| `<img src="x" onerror="alert(1)">` | ✅ вырезано |
| `<img src=x onerror=alert(1)>` | ❌ **прошло** |
| `<body onload=alert(1)>` | ❌ **прошло** |
| `<iframe src="javascript:alert(1)"></iframe>` | ❌ **прошло** |
| `<button formaction="javascript:alert(1)">` | ❌ **прошло** |
| `<a href="javascript:alert(1)">` | ✅ заменено на `#` |

Причина: регулярки `\son[a-z]+\s*=\s*"[^"]*"` и `...'[^']*'` требуют кавычек; `javascript:` нейтрализуется только внутри `<a href>`.

**Модель угрозы реальна:** `book.html` — это файл, который пользователь открывает в браузере, а тело книги приходит из недоверенного EPUB/PDF (через Calibre → pandoc → чанки). Ничто не мешает источнику содержать `<img src=x onerror=...>`.

**Тестовый пробел:** `tests/test_mab_html.py` покрывает только кавычные варианты (`:50`), а `tests/integration_smoke.py:83–87` кладёт в «враждебный» контент `<p onload="...">` в кавычках и `<a href="javascript:...">` — то есть CI зелёный при наличии дыр.

**Как починить:** заменить денилист на allowlist-санитайзер (`nh3` — обёртка над ammonia, или `bleach`), либо, как минимум:

- добавить ветки для безкавычных значений: `\son[a-z]+\s*=\s*[^\s>"']+`;
- расширить URL-правило на `(?:href|src|formaction|poster|xlink:href)`;
- удалять целиком `<iframe>`, `<object>`, `<embed>`, `<svg>` с обработчиками;
- добавить 4 теста из таблицы выше.

---

### C-05 🟠 `manifest.json`: неатомарная запись + необработанные ошибки чтения в гейте целостности

**Где:** `scripts/manifest.py:33–69` (запись), `:72–78` (чтение), `:98` (`manifest["chunks"]`)

```python
with open(manifest_path, 'w', encoding='utf-8') as f:   # :66 — пишем поверх, без tmp+rename
    json.dump(manifest, f, indent=2, ensure_ascii=False)
...
return json.load(f)                                      # :78 — без try/except
...
for chunk in sorted(manifest["chunks"], ...):            # :98 — KeyError, если ключа нет
```

**Доказано пробами:**

```
[F] validate_for_merge raised JSONDecodeError: Expecting value: line 1 column 31 (char 30)
[I] create_manifest writes in place: True  → BUG - non-atomic write (truncated file on crash)
[G] validate_for_merge raised KeyError: 'chunks'
```

Это тот самый гейт, который должен защищать от неполной книги (см. C-01). Вместо внятного «manifest.json повреждён, пересоздайте» пользователь получает стектрейс — причём ровно в той ситуации, когда он и так уже в аварии (процесс убили посреди записи). Соседние модули (`glossary.save_glossary`, `meta`, `run_state`) пишут атомарно — `manifest.py` выбивается из собственного стандарта проекта.

**Как починить:** `tempfile.NamedTemporaryFile(dir=temp_dir, delete=False)` + `os.replace()`; в `load_manifest` ловить `(OSError, json.JSONDecodeError)` и возвращать `None` с сообщением; в `validate_for_merge` брать `manifest.get("chunks")` и при не-списке возвращать ошибку валидации, а не падать.

---

### C-06 🟠 `SKILL.md`: правило экранирования кавычек противоречит само себе

**Где:** `SKILL.md:317–318`

```
- 错误示例：`alt="爱丽丝拿着标着"喝我"的瓶子"` ← 内层英文 `"` 把外层 alt 撑断了
- 正确示例：`alt="爱丽丝拿着标着"喝我"的瓶子"` 或 `alt="爱丽丝拿着标着&quot;喝我&quot;的瓶子"`
```

Строки **байт-в-байт идентичны** в первой части: строка, объявленная ошибочной, тут же предъявлена как правильная. Агент, выполняющий эту инструкцию, получает прямо противоположные указания в единственном месте, где описано экранирование `alt` — и с высокой вероятностью сгенерирует битые `alt`-атрибуты (что потом ловит `_check_generated_html_sanity`, но уже поздно).

Рядом — загрязнение русского промпта китайскими вставками:

- `SKILL.md:225`: `…не удаляйте отдельные цифровые строки (годы 1984, номера глав, номера引用 и т.д.)`
- `SKILL.md:279`: `…для определения местоимений, рода, псевдонимов и跨 fragment ссылок; пустое поле — пропустите`

`SKILL.md` — это не документация, а исполняемый промпт скилла: агент читает его дословно. Ошибки здесь дороже, чем в README.

**Как починить:** в «правильном» примере оставить только `&quot;`-вариант (и, если нужно, `&#34;`), китайские слова заменить (`номера ссылок`, `межфрагментных ссылок`), добавить регресс-тест на отсутствие CJK в русских секциях (простая проверка диапазона U+4E00–U+9FFF по строкам вне китайских блоков).

---

## 4. Средние и низкие

### C-07 🟡 `merge_meta.py` падает трейсбеком без `glossary.json`

`merge_meta.py:146` (`prepare-merge`) и `:505` (`apply-merge`) вызывают `load_glossary`, который на отсутствующем файле делает `raise FileNotFoundError`. `main()` (`:1031`) ничем это не ловит:

```
[H] exit=1 stderr_tail=[... 'FileNotFoundError: Glossary not found: ...\\glossary.json']
[H] VERDICT: BUG - raw traceback when glossary.json is absent
```

По штатному процессу (SKILL.md §3.5) глоссарий создаётся до перевода, но SKILL.md §161 прямо допускает работу без него, а пользователь может удалить файл руками. Ожидаемое поведение — сообщение «глоссарий не найден, сначала выполните …» и код возврата 2, а не стектрейс. Правка на 5 строк в `main()`.

### C-08 🟡 `generate_formats()` возвращает `None` вместо `False`

`_mab_formats.py:103–104`:

```python
print("No HTML files found for format generation")
return                      # ← None
```

Тип возврата функции — «bool», `main()` использует `if not all_formats_ok`, поэтому сейчас последствий нет (просто печатается «Some output formats failed», хотя причина другая). Но это ловушка на будущее: любая проверка `is False` или `== False` сломается. Пробa: `[E] generate_formats on empty dir returned None`.

### C-09 🟡 `--cleanup` необратим, а `.bat` передаёт его всегда

`merge_and_build.py:74` (`cleanup_intermediate_files`) удаляет `chunk*.md`, `output_chunk*.md`, `input.html`, `input.md`, `output.html`. После этого повторный `merge_and_build` **невозможен**: `validate_for_merge` не найдёт `output_chunk*.md` и завершится с `Missing output: …`.

В связке с C-02 это даёт тупик: поправить название книги или шрифт после `--cleanup` нельзя ничем, кроме полного повторного перевода. `translate-launcher.bat:129` всегда добавляет `--cleanup`, а SKILL.md §10 показывает его же в примере.

Минимум — флаг `--cleanup` должен печатать, что именно удаляется, и требовать `--cleanup-force` при наличии `output_chunk*.md`; лучше — удалять только `input.html`/`output.html`/`output.md`, оставляя чанки.

### C-10 🟡 `translate-launcher.bat`: пять расхождений с реальностью

| Строка | Проблема |
|---|---|
| `:7`, `:54` | «Supported: EPUB, PDF, DOCX, **TXT**» — `convert.py` отвечает `Error: Unsupported file type: .txt`, exit 1 (проверено) |
| `:31` | фильтр файлового диалога содержит `*.txt` — пользователь может выбрать файл, который гарантированно не откроется |
| `:21` | баннер `v1.0` при версии 1.2.1 |
| `:129` | `--title "%BOOK_NAME%"` — затирает `original_title` из `config.txt` именем файла/папки |
| `:88` | голый `pip install pypandoc beautifulsoup4` — может поставить пакеты не в тот интерпретатор, которым потом запускается `python` (нужно `python -m pip`) |
| `:137–142` | результаты переносятся только при наличии `book.epub`; если EPUB упал, а DOCX/PDF собрались — не переносится ничего |
| `:130–134` | после v1.2.1 код возврата 1 означает «формат не собрался», а сообщение — «translation may not be complete yet» (вводит в заблуждение при сбое Calibre) |

### C-11 🟡 `create-desktop-shortcut.ps1:11` — PowerShell 6+ синтаксис

```powershell
Write-Host "`u{2705} Shortcut created: $($s.FullName)"
```

Эскейп `` `u{...} `` появился в PowerShell 6. Под Windows PowerShell 5.1 (а `.ps1` обычно запускают именно им) выведется буквально `` `u{2705} ``. Замена: `"$([char]::ConvertFromUtf32(0x2705)) Shortcut created: ..."`.

### C-12 🟡 Мёртвые дефолты `target_size=6000`

`convert.py:574` и `:686` объявляют `target_size=6000`, а CLI (`--chunk-size`) по умолчанию 15000. При программном вызове (а именно так делают `tests/integration_smoke.py` и возможные внешние скрипты) получится вдвое больше чанков, чем при запуске через CLI. Стоит либо поднять дефолты до 15000, либо брать их из одной константы.

---

## 5. Документация

### D-01 🟡 `ARCHITECTURE.md`: устаревшие цифры и «пять форматов»

- `:14` и `:124` — «each ~6000 chars» (фактический дефолт 15000)
- `:179` и `:185` — «**five** output formats», а перечислено четыре: HTML, DOCX, EPUB, PDF
- `:191` — «new input formats need zero pipeline changes», тогда как `convert.py` жёстко проверяет расширение (`.pdf/.docx/.epub`) и отвергает всё прочее (в т.ч. `.txt`)

### D-02 🟡 «~6000-char chunks» в трёх README

`README.md:18`, `README.ru.md:18`, `README.zh-CN.md:143`. При дефолте 15000 цифра занижает размер в 2,5 раза и провоцирует неверные ожидания по числу чанков и стоимости.

### D-03 🟡 Метрики бейзлайнов невоспроизводимы

`tests/baselines/README.md:14` — колонка «Chunks (**target_size=6000**)»; `tests/baselines/standard-alice/SOURCE.md` фиксирует «`chunk_count == 38`, `target_size=6000`, default concurrency 8». Текущие дефолты — 15000 и 24, а сам фикстур `standard-alice.epub` с v1.2.1 в git не хранится (качается по ссылке). Любое значение из таблицы «Measured» нельзя ни проверить, ни воспроизвести без ручной перенастройки.

### D-04 🟡 `SKILL.md`: путь вывода и противоречие по concurrency

- `:501` — «Final files go to: `test-output/book.{epub,docx,pdf,html}`». Фактически файлы остаются в `test-output/<book>_temp/` (`_mab_formats.generate_format` пишет `os.path.join(temp_dir, f"book{ext}")`); в `test-output/` их переносит только `.bat`.
- `:19` и `:137` — «concurrency (default: 24)»; `:140` — «max 3 per batch for this user; adjust concurrency accordingly». Одно и то же слово означает «размер батча скилла» и «лимит одного вызова `delegate_task`». Нужно развести формулировки: `concurrency` = сколько задач в батче, `delegate_task` принимает ≤3 задач за вызов ⇒ батч из 24 задач = 8 вызовов. Менять сам дефолт без решения владельца не предлагаю.
- `README.ru.md:144–145` рекомендует `concurrency: 1` для 8 ГБ — при этом PRO-версия заявлена как «32GB+ RAM». Формально не противоречие (это оговорка для слабого железа), но стоит согласовать с `setup.py`, который ругается при <32 ГБ.

---

## 6. Уже исправлено в v1.2.1 — повторно не чинить

Проверено диффом `cde660b..8a1606a` и запуском тестов дерева `8a1606a`.

| Ранее найденное | Статус в `8a1606a` |
|---|---|
| `_mab_toc` regex-фолбэк: `\g` в `re.sub` ронял сборку, заголовки с атрибутами не получали `id` (висячие якоря) | ✅ закрыто (callback, id для `<h2 class=…>`, переиспользование pandoc-id, экранирование текста) |
| XSS через `title`/`author` из метаданных книги; сам санитайзер | ✅ добавлены `html.escape` + `sanitize_html_body` (но см. C-04 — обход) |
| `merge_and_build` возвращал 0 при провале генерации форматов | ✅ `sys.exit(1)` |
| `convert.py` ломал настоящие markdown-ссылки `[**Chapter 1**](url)` | ✅ negative lookahead `(?![\[(])` |
| `glossary` не учитывал границы слов для кириллицы | ✅ граница для не-ASCII |
| Краш `setup.py` на emoji при перенаправлении вывода (cp1251/cp866) | ✅ ASCII-вывод |
| `subprocess` декодировал вывод в cp1251 и падал | ✅ `encoding='utf-8', errors='replace'` |
| URL клонирования без `-pro`, имя каталога скилла, `skill_view(name=…)` | ✅ во всех README |
| `AGENTS.md`: `git push origin main` при ветке `master` | ✅ `master` |
| `CLAUDE.md` описывал чужой проект (`deusyu/translate-book`, ClawHub), требовал несуществующий `.claude/commands/release.md` и запрещал mtime-логику, которая уже была в коде | ✅ переписан как ссылка на `AGENTS.md` |
| «concurrency default 8» в `ARCHITECTURE.md` vs 24 в `SKILL.md` | ✅ унифицировано на 24 (с оговоркой про лимит 3) |
| 11 МБ `standard-alice.epub` и осиротевший `hermes-time-machine-test-v2.epub` в git | ✅ убраны, добавлены инструкции по скачиванию |
| CI без реального прогона пайплайна; actions без пиннинга | ✅ добавлен `integration` job на `sleepy-hollow`, actions запинены по SHA, матрица 3.9–3.13 |
| Тестов: 226 | ✅ 271 (`Ran 271 tests … OK`) |

---

## 7. Тесты и покрытие

- Локально: `python -m unittest discover -s tests -p 'test_*.py'` → **226 тестов, OK**.
- Дерево `8a1606a`: **271 тест, OK** (прогнано из `git archive` в `%TEMP%`, репозиторий не тронут).
- `ast.parse(..., feature_version=(3,9))` для всех `scripts/*.py` и `tests/*.py` — несовместимостей с Python 3.9 нет.
- `ruff check scripts tests` → 148 замечаний (в основном `I001` порядок импортов, `BLE001` широкие `except`, `RUF100` лишние `noqa`); `pyflakes` — только намеренный реэкспорт в `merge_and_build.py` и неиспользуемый `sys` в `_mab_merge.py`. Неопределённых имён нет.

**Пробелы (по дереву `8a1606a`, 72 из 129 функций ни разу не упомянуты в тестах):**

| Не покрыто | Почему это важно |
|---|---|
| `convert._do_split_and_manifest`, `_find_existing_chunk_files` | в них живёт C-01 |
| `manifest.load_manifest`, `file_hash` | в них живёт C-05 |
| `merge_and_build.cleanup_intermediate_files` | деструктивная операция без теста (C-09) |
| `convert._abort_on_source_cache_mismatch`, `_has_reusable_source_cache`, `_load_source_fingerprint` | защита от подмены исходника |
| `convert.convert_to_htmlz`, `extract_htmlz`, `extract_metadata_from_htmlz`, `convert_html_to_markdown` | основной путь конвертации (в CI его гоняет только integration-smoke) |
| `calibre_html_publish.prepare_html_for_conversion`, `copy_images_if_needed`, `_get_pdf_font_for_lang` | шрифт для CJK-PDF и перенос картинок — типичное место «квадратиков» в PDF |
| `run_state.save_run_state`, `build_chunk_record` | выборочный повторный перевод |
| `_mab_html.convert_with_pandoc` | основной конвертер MD→HTML (в юнит-джобе pandoc заведомо отсутствует) |

Это не «плохое покрытие вообще» — набор тестов заметно вырос и покрывает логику глоссария, манифест-гейт, TOC и санитайзер. Но именно перечисленные пути либо не имеют тестов, либо проверяются только на одном бейзлайне в integration-джобе.

---

## 8. CI

`.github/workflows/ci.yml` (v1.2.1):

1. `cache-dependency-path: scripts/setup.py` — `setup.py` не содержит списка зависимостей (это скрипт проверки окружения). Кэш ключуется по файлу, который не меняется при изменении зависимостей.
2. `pip install pypandoc beautifulsoup4` — без пиннинга версий и без `requirements.txt`/`pyproject.toml` в репозитории. Actions запинены по SHA (хорошо), а Python-зависимости — нет: сборка невоспроизводима.
3. Нет шага линта (`ruff`), хотя 148 замечаний уже накоплено — то есть дешёвый гейт качества не подключён.
4. Юнит-джоба не ставит calibre/pandoc (всё замокано) — это осознанное решение, но означает, что ветки с реальным `subprocess` проверяются только в одном integration-джобе на одном бейзлайне.
5. Матрица 3.9–3.13; локально используется Python **3.14.3**, его в матрице нет.

---

## 9. Безопасность

Скан 55 отслеживаемых файлов (без бинарников):

| Категория | Найдено |
|---|---|
| API-ключи, токены, `ghp_*`, `sk-*`, AWS/GCP | 0 |
| `password`/`secret`/`token` с присваиванием | 0 |
| Приватные IP, e-mail | 0 |
| Абсолютные локальные пути | 2 (безопасно): `AGENTS.md` → `C:\Users\<user>` (плейсхолдер), `TEST_RESULTS.md` → `/f/translate-book-parallel-pro` |
| `shell=True`, `os.system`, `eval`, `exec`, `pickle`, `yaml.load` | 0 (все `subprocess` — списком аргументов; в `setup.py:53` это отмечено комментарием) |

Единственная реальная тема безопасности — C-04 (санитайзер `book.html` против враждебного исходного файла).

---

## 10. План исправлений

**P0 — до следующего реального перевода книги**

1. `git pull --ff-only origin master` (получить v1.2.1; дерево чистое).
2. **C-01** — проверка полноты набора чанков в `_do_split_and_manifest` + тесты на дырку в нумерации и на усечённый чанк.
3. **C-02** — штамп метаданных (md-hash + title + author + lang + mtime шаблонов) в `_mab_html`/`_mab_formats`; не пропускать генерацию, если `book.html` отсутствует.
4. **C-05** — атомарная запись + мягкая обработка битого/неполного манифеста.

**P1 — качество и стоимость**

5. **C-06** — исправить `SKILL.md:317–318`, убрать CJK из `:225`/`:279`, поправить `:501`, развести формулировки про concurrency.
6. **C-03** — мягкий порог разрезки по заголовку.
7. **C-04** — allowlist-санитайзер или расширение правил + 4 теста.
8. **C-09** — не удалять чанки по умолчанию (или требовать `--cleanup-force`).

**P2 — гигиена**

9. **C-07**, **C-08**, **C-10**, **C-11**, **C-12** — точечные правки, каждая на 1–10 строк.
10. **D-01…D-04** — цифры 6000 → 15000, «five» → «four», метрики бейзлайнов пересчитать под текущие дефолты либо явно пометить «историческое измерение».
11. **T-02** — `requirements.txt` с пиннингом, `ruff` в CI, осмысленный `cache-dependency-path`.

**P3 — покрытие**

12. Тесты на `cleanup_intermediate_files`, `_do_split_and_manifest`, `manifest.load_manifest` (битый JSON), `prepare-html`+PDF-шрифт для CJK.

---

## 11. Как воспроизвести

Все пробы лежат вне репозитория, пишут только в `tempfile.mkdtemp()`:

```
%TEMP%\opencode\audit_demo.py        — C-01, C-03, C-02, TOC-якоря (в cde660b), C-08
%TEMP%\opencode\audit_demo2.py       — C-05 (JSON/KeyError/атомарность), C-07, .txt
%TEMP%\opencode\audit_demo3.py       — C-04 (обход санитайзера, код из 8a1606a)
%TEMP%\opencode\audit_coverage.py    — покрытие по дереву cde660b
%TEMP%\opencode\audit_secret_scan.py — скан секретов
%TEMP%\opencode\remote_tree\         — git archive 8a1606a (для прогона 271 теста)
```

Основные команды:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v     # 226 (cde660b) / 271 (8a1606a)
python C:\Users\User\AppData\Local\Temp\opencode\audit_demo.py
python C:\Users\User\AppData\Local\Temp\opencode\audit_demo2.py
python C:\Users\User\AppData\Local\Temp\opencode\audit_demo3.py
```

---

## 12. Что в проекте сделано хорошо

Чтобы список проблем не создавал искажённой картины:

- **Гейт целостности перевода** (`validate_for_merge`): проверка хешей исходных чанков, наличия вывода, пустых/пробельных файлов, «подозрительно коротких» переводов — заметно выше среднего для подобных пайплайнов.
- **Привязка temp-каталога к байтам исходника** (`source_fingerprint.json` + `_abort_on_source_cache_mismatch`) — защита от молчаливого переиспользования чанков после подмены файла.
- **Атомарная запись** в `glossary.py`, `meta.py`, `run_state.py` (единственный выпадающий — `manifest.py`, см. C-05).
- **Проверка структуры изображений** (`_mab_images`) — сравнение ссылок до/после перевода и санити-чек готового HTML.
- **Тесты**: 271 штука, быстрые (2 с), с осмысленными именами и моками внешних инструментов; integration-smoke реально гоняет Calibre+pandoc в CI.
- **Дисциплина документации**: трёхъязычные README, CHANGELOG с описанием причин, разделение обязанностей между `SKILL.md` (промпт) и `ARCHITECTURE.md` (устройство).
