# Translate Book Parallel

[English](README.md) | [Русский](README.ru.md)

**Hermes Agent Skill** — translates entire books (PDF/DOCX/EPUB) into any language using parallel sub-agents with a resumable chunked pipeline.

> Ported from [deusyu/translate-book](https://github.com/deusyu/translate-book) (Rainman Translate Book) for Hermes Agent.  
> Original inspired by [claude_translater](https://github.com/wizlijun/claude_translater).

---

## How It Works

```
Input (PDF/DOCX/EPUB)
  │
  ▼
Calibre → HTMLZ → Markdown (~6000-char chunks)
  │
  ▼
Parallel sub-agents (Hermes delegate_task)
  │  each translates 1 chunk in isolated context
  ▼
Validate → Merge → Build
  │
  ▼
HTML / DOCX / EPUB / PDF
```

Each chunk gets its own independent sub-agent with a fresh context window. This prevents context overflow and output truncation that plague single-session book translation.

## Features

- **Parallel translation** — multiple chunks translated concurrently via `delegate_task`
- **Resumable** — automatically skips already-translated chunks on re-run
- **Glossary-driven term consistency** — sub-agents share a canonical term table
- **Selective re-translation** — only re-translate chunks affected by glossary edits
- **Neighbor context** — each chunk sees short excerpts from adjacent chunks for pronoun/entity resolution
- **Integrity validation** — SHA-256 hashes prevent stale/corrupt output from being merged
- **Multi-format output** — HTML (floating TOC), DOCX, EPUB, PDF
- **Format-agnostic input** — PDF, DOCX, EPUB all handled by Calibre
- **Multi-language** — zh, en, ja, ko, fr, de, es (extensible)

## Prerequisites

| Dependency | Required | Install |
|-----------|----------|---------|
| **Python 3.8+** | Yes | `python --version` |
| **Calibre** (ebook-convert) | Yes | [calibre-ebook.com](https://calibre-ebook.com/) |
| **Pandoc** | Yes | `winget install JohnMacFarlane.Pandoc` |
| **pypandoc** | Yes | `pip install pypandoc` |
| **beautifulsoup4** | Recommended | `pip install beautifulsoup4` |

Verify all tools:

```bash
ebook-convert --version
pandoc --version
python -c "import pypandoc; print('pypandoc ok')"
```

## Installation (Hermes)

```bash
# 1. Clone the repository
git clone https://github.com/L-MORIA/translate-book-parallel.git
cp -r translate-book-parallel "${HERMES_HOME:-$HOME/.hermes}/skills/translate-book-parallel"

# 2. Reload skills in Hermes
# Run /reload-skills in the chat
```

Verify:

```bash
skill_view(name='translate-book-parallel')
# → readiness_status: available
```

## Usage

Once installed, tell Hermes to translate a book in natural language:

```
translate D:\books\clean-code.epub to Russian
```

```
translate /path/to/book.pdf to Chinese using parallel sub-agents
```

### Manual pipeline steps

```bash
# 1. Convert to chunks
python scripts/convert.py /path/to/book.pdf --olang ru

# 2. Build glossary (optional, for term consistency)
# (handled automatically by the skill)

# 3. Translate — handled by the skill via delegate_task

# 4. Merge and build output formats
python scripts/merge_and_build.py --temp-dir book_temp --title "Название книги"
```

Outputs in `book_temp/`:

| File | Format |
|------|--------|
| `output.md` | Merged translated Markdown |
| `book.html` | Web version with floating TOC |
| `book_doc.html` | Ebook HTML |
| `book.docx` | Word document |
| `book.epub` | EPUB ebook |
| `book.pdf` | PDF (print-ready) |

## Supported Languages

| Code | Language |
|------|----------|
| `zh` | Chinese |
| `en` | English |
| `ja` | Japanese |
| `ko` | Korean |
| `ru` | Russian |
| `fr` | French |
| `de` | German |
| `es` | Spanish |

Language codes are extensible — add new ones to the skill triggers in `SKILL.md`.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full pipeline diagram and component descriptions.

## What Was Changed from Original

See [CHANGELOG.md](CHANGELOG.md) for the complete list of Hermes-specific adaptations.

## License

MIT — same as the original [deusyu/translate-book](https://github.com/deusyu/translate-book).
