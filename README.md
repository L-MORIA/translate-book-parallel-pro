# Translate Book Parallel

[English](README.md) | [Русский](README.ru.md)

**Agent Skill** — translates entire books (PDF/DOCX/EPUB) into any language using parallel sub-agents with a resumable chunked pipeline.

Originally packaged for Hermes Agent. The pipeline itself is host-agnostic: it runs on OpenCode, Claude Code, Codex, or any agent with shell/file tools and a sub-agent primitive — see [AGENT_ADAPTER.md](AGENT_ADAPTER.md).

> Ported from [deusyu/translate-book](https://github.com/deusyu/translate-book) (Rainman Translate Book) for Hermes Agent.  
> Original inspired by [claude_translater](https://github.com/wizlijun/claude_translater).

---

## How It Works

```
Input (PDF/DOCX/EPUB)
  │
  ▼
Calibre → HTMLZ → Markdown (~15000-char chunks)
  │
  ▼
Parallel sub-agents (host delegate/Task tool)
  │  each translates 1 chunk in isolated context
  ▼
Validate → Merge → Build
  │
  ▼
HTML / DOCX / EPUB / PDF
```

Each chunk gets its own independent sub-agent with a fresh context window. This prevents context overflow and output truncation that plague single-session book translation.

## Features

- **Parallel translation** — multiple chunks translated concurrently via the host's subagent/Task tool
- **Resumable** — automatically skips already-translated chunks on re-run
- **Glossary-driven term consistency** — sub-agents share a canonical term table
- **Selective re-translation** — only re-translate chunks affected by glossary edits
- **Neighbor context** — each chunk sees short excerpts from adjacent chunks for pronoun/entity resolution
- **Integrity validation** — SHA-256 hashes prevent stale/corrupt output from being merged
- **Multi-format output** — HTML (floating TOC), DOCX, EPUB, PDF
- **Format-agnostic input** — PDF, DOCX, EPUB all handled by Calibre
- **Multi-language with dedicated prompts** — zh (Chinese), ru (Russian), en, ja, ko, fr, de, es

## Prerequisites

| Dependency | Required | Install |
|-----------|----------|---------|
| **Python 3.9+** | Yes | `python --version` |
| **Calibre** (ebook-convert) ≥ 9.x | Yes | [calibre-ebook.com](https://calibre-ebook.com/) or `winget upgrade calibre.calibre` |
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
git clone https://github.com/L-MORIA/translate-book-parallel-pro.git

# 2. Install dependencies
python scripts/setup.py

# 3. Install the skill in Hermes
cp -r translate-book-parallel-pro "${HERMES_HOME:-$HOME/.hermes}/skills/translate-book-parallel-pro"

# 4. Reload skills in Hermes
# Run /reload-skills in the chat
```

Verify:

```bash
skill_view(name='translate-book-parallel-pro')
# → readiness_status: available
```

## Usage

Once installed, tell Hermes to translate a book in natural language:

```
translate /path/to/book.epub to Russian
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

## Roadmap

See [ROADMAP.md](ROADMAP.md). The primary direction is an MCP server so the
same pipeline runs in OpenCode, Claude Code, Codex, ZCode, MiniMax Code, Kimi
and any other MCP-capable agent; headless orchestration and installable host
adapters are the intermediate steps.

The **MCP server MVP is implemented (v1.3.0)** — stdio, stdlib-only JSON-RPC,
no SDK dependency:

```bash
python scripts/mcp_server.py --workspace /path/to/books
```

Tools: `convert_book`, `get_status`, `get_translation_plan`, `get_chunk_prompt`,
`submit_translation`, `merge_meta`, `validate_book`, `build_book`. The server
never calls an LLM — the host agent translates the prompts it returns (itself
or via its sub-agents). Remaining: packaging (M4) and HTTP transport (M5).

## Known Issues

- **Memory:** with `concurrency > 1` on systems with 8 GB RAM, memory exhaustion is possible.
  Workaround: use `concurrency: 1` in the translation configuration.
  `scripts/setup.py` includes a built-in RAM check.

## What Was Changed from Original

See [CHANGELOG.md](CHANGELOG.md) for the complete list of host-specific adaptations.

## License

MIT — same as the original [deusyu/translate-book](https://github.com/deusyu/translate-book).
