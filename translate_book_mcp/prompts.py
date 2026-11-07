"""Translation prompt templates for the MCP server.

`build_chunk_prompt()` assembles the same prompt a sub-agent receives through
SKILL.md §4: the task line, the translation rules, the per-chunk term table
(rule #13, omitted when empty — SKILL.md documents empty stdout from
`glossary.py print-terms-for-chunk` as "no glossary") and the read-only
neighbor context (omitted when empty).

The rule texts are copies of the SKILL.md §4 templates. tests/
test_mcp_tools.py::PromptSyncTests guards the most load-bearing phrases
against drift between the two files.
"""

RU_RULES = """1. Строго сохраняйте Markdown-разметку: заголовки, ссылки, изображения
2. Переводите только текст, не трогайте Markdown-синтаксис и имена файлов
3. Удаляйте пустые ссылки, лишние символы и знаки `\\` в конце строк. Номера страниц уже обработаны convert.py — не удаляйте отдельные цифровые строки (годы 1984, номера глав, номера ссылок и т.д.)
4. Обеспечьте точность перевода при естественном и плавном стиле
5. Выводите ТОЛЬКО переведённый текст — никаких пояснений, комментариев, диалогов
6. Используйте ясные и краткие формулировки. Переводите последовательно, не пропускайте содержимое
7. Сохраняйте все ссылки на изображения: `![alt](path)` полностью сохраняется, пути не меняйте, alt-текст можно перевести; HTML-атрибуты (`alt`, `title`) внутри тегов должны остаться валидными — заменяйте `"`→« », `'`→« », `<`→`&lt;`, `>`→`&gt;`, `&`→`&amp;` только внутри значений атрибутов; `src`/`href` не меняйте
8. Распознавайте иерархию заголовков и сохраняйте уровни существующих Markdown-заголовков
9. Короткий обобщающий текст на отдельной строке — вероятно заголовок; не добавляйте лишних заголовков
10. Абзацы не маркируйте как заголовки
11. Переводите последовательно, ничего не пропускайте"""

GENERIC_RULES = """1. Preserve Markdown structure strictly: headings, links, images
2. Translate text only; do not touch Markdown syntax or file names
3. Remove empty links, stray symbols and trailing backslashes. Do not remove standalone numeric lines (years, chapter numbers, citation numbers)
4. Ensure translation accuracy with a natural, fluent style
5. Output ONLY the translated text — no explanations or commentary
6. Use clear, concise wording; translate sequentially without skipping content
7. Preserve all image links `![alt](path)`; keep paths unchanged, alt text may be translated; HTML tag attributes (`alt`, `title`) must stay valid — replace `"`, `'`, `<`, `>`, `&` with safe analogues only inside attribute values; never change `src`/`href`
8. Recognize heading hierarchy; keep the levels of existing Markdown headings
9. A short summarizing line on its own line is likely a heading; do not invent extra headings
10. Do not mark ordinary paragraphs as headings
11. Translate sequentially, skipping nothing"""

META_NOTE_RU = (
    "4. Запишите наблюдения в файл {meta_path} по схеме meta (schema_version 1; "
    "массивы можно оставлять пустыми — не выдумывайте сущности; НЕ добавляйте поле chunk_id). "
    "Пустая мета — валидный результат."
)
META_NOTE_GENERIC = (
    "4. Write observations to {meta_path} following the meta schema "
    "(schema_version 1; arrays may stay empty — do not invent entities; "
    "do NOT add a chunk_id field). An empty meta is a valid result."
)

RULE13_HEADER_RU = (
    "13. Единообразие терминов: следующие термины нужно строго использовать "
    "в указанном переводе. Если в тексте встречается форма из столбца «оригинал» "
    "**или** столбца «псевдонимы», она должна быть переведена в форму из столбца «перевод»."
)
RULE13_HEADER_GENERIC = (
    "13. Term consistency: use exactly the following translations. If a form "
    "from the 'original' **or** 'aliases' column appears in the text, it must "
    "be rendered as the 'translation' column says."
)

NEIGHBOR_HEADER_RU = (
    "Контекст соседних фрагментов (только для чтения, не переводить, "
    "не включать в вывод; используется для определения местоимений, рода, "
    "псевдонимов и межфрагментных ссылок; пустое поле — пропустите):"
)
NEIGHBOR_HEADER_GENERIC = (
    "Neighbor chunk context (read-only; do not translate or include in the "
    "output; used for pronoun, gender, alias and cross-chunk resolution):"
)

TEMPLATES = {
    'ru': {
        'rules': RU_RULES,
        'task': (
            "Переведите файл-источник `{source_path}` на {target_language} и "
            "запишите результат в `{output_path}`. Соблюдайте правила ниже. "
            "Выводите только переведённый текст."
        ),
        'meta': META_NOTE_RU,
        'rule13': RULE13_HEADER_RU,
        'neighbor': NEIGHBOR_HEADER_RU,
        'source_header': "Текст markdown-файла:",
    },
    'generic': {
        'rules': GENERIC_RULES,
        'task': (
            "Translate the source file `{source_path}` into {target_language} "
            "and write the result to `{output_path}`. Follow the rules below. "
            "Output only the translated text."
        ),
        'meta': META_NOTE_GENERIC,
        'rule13': RULE13_HEADER_GENERIC,
        'neighbor': NEIGHBOR_HEADER_GENERIC,
        'source_header': "Markdown source text:",
    },
}


def _template_for(target_language):
    """Pick the template by target language; 'ru' gets the Russian template."""
    lang = (target_language or '').strip().lower()
    return TEMPLATES['ru'] if lang.startswith('ru') else TEMPLATES['generic']


def build_chunk_prompt(source_path, output_path, meta_path, target_language,
                       term_table='', neighbor_context=''):
    """Assemble the full per-chunk translation prompt.

    `term_table` is the 3-column markdown table from
    `glossary.format_terms_for_prompt()` — empty means no glossary or no
    relevant terms, and rule #13 is omitted entirely (SKILL.md contract).
    `neighbor_context` is the rendered block from
    `chunk_context.format_for_prompt()` — omitted when empty.
    """
    tpl = _template_for(target_language)
    parts = [
        tpl['task'].format(source_path=source_path, output_path=output_path,
                           target_language=target_language),
        "ВАЖНЫЕ ТРЕБОВАНИЯ:" if tpl is TEMPLATES['ru'] else "REQUIREMENTS:",
        tpl['rules'],
        tpl['meta'].format(meta_path=meta_path),
    ]
    if term_table:
        parts.append(tpl['rule13'])
        parts.append(term_table)
    if neighbor_context:
        parts.append(tpl['neighbor'])
        parts.append(neighbor_context)
    parts.append(tpl['source_header'])
    return '\n\n'.join(parts)


REVIEW_PROMPT_RU = (
    "Проверьте перевод в `{output_path}` против исходника `{source_path}` "
    "(язык: {target_language}). Найдите пропущенные фрагменты, сломанную "
    "Markdown-разметку, потерянные ссылки на изображения и непоследовательную "
    "терминологию. Верните список проблем с цитатами; если всё в порядке — "
    "напишите «OK»."
)
REVIEW_PROMPT_GENERIC = (
    "Review the translation in `{output_path}` against the source `{source_path}` "
    "(language: {target_language}). Look for missing content, broken Markdown "
    "structure, lost image links and inconsistent terminology. Return a list of "
    "issues with quotes; write \"OK\" if everything is fine."
)


def build_review_prompt(source_path, output_path, target_language):
    lang = (target_language or '').strip().lower()
    template = REVIEW_PROMPT_RU if lang.startswith('ru') else REVIEW_PROMPT_GENERIC
    return template.format(
        source_path=source_path, output_path=output_path,
        target_language=target_language,
    )
