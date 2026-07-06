# Architecture: translate-book-parallel

```
┌─────────────────────────────────────────────────────────────────────┐
│                     INPUT (PDF / DOCX / EPUB)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 1: CONVERT (Calibre + Pandoc)                   │
│                                                                     │
│  ebook-convert → HTMLZ → input.html → input.md                     │
│                                                                     │
│  Output: chunk0001.md ~ chunk00NN.md (each ~6000 chars)            │
│          manifest.json  (SHA-256 hashes for integrity)              │
│          source_fingerprint.json  (SHA-256 of source bytes)         │
│          config.txt  (pipeline metadata + original title)           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 2: BUILD GLOSSARY (optional)                    │
│                                                                     │
│  Sample chunks → extract terms → glossary.json                     │
│  glossary.py count-frequencies → frequency stats                   │
│                                                                     │
│  Purpose: ensure term consistency across all chunks                │
│  Each sub-agent receives a per-chunk term table                    │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 3: PLAN SELECTIVE RE-TRANSLATION                │
│                                                                     │
│  run_state.py plan → which chunks need translation:                │
│    • translation_chunk_ids   (need LLM)                            │
│    • record_only_chunk_ids   (already valid, just register)        │
│    • unchanged_chunk_ids     (skip entirely)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 4: PARALLEL TRANSLATION                         │
│                                                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     ┌──────────┐        │
│  │sub-agent │  │sub-agent │  │sub-agent │ ... │sub-agent │        │
│  │  chunk01 │  │  chunk02 │  │  chunk03 │     │  chunkN  │        │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     └────┬─────┘        │
│       │             │             │                │              │
│       ▼             ▼             ▼                ▼              │
│  output_chunk01  output_chunk02  output_chunk03   output_chunkN   │
│  output_chunk01.meta.json  ...  (sub-agent observations)          │
│                                                                     │
│  Batching: up to concurrency sub-agents per batch (default: 8)     │
│  Hermes delegate_task: max 3 concurrent (configurable)             │
│  Each sub-agent gets:                                              │
│    • 1 chunk file (read)                                           │
│    • target language                                               │
│    • translation prompt (Markdown-safe rules)                      │
│    • per-chunk term table (from glossary)                          │
│    • neighbor context (read-only ±300 chars)                       │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 4.5: MERGE META BACK TO GLOSSARY                │
│                                                                     │
│  After each batch:                                                  │
│  1. run_state.py record — mark chunks complete                     │
│  2. merge_meta.py prepare-merge — scan meta files                  │
│  3. resolve decisions (auto_apply + manual)                        │
│  4. merge_meta.py apply-merge → glossary enriched                  │
│                                                                     │
│  Purpose: propagate entity discoveries from later chunks            │
│           back to earlier chunk term tables                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 5: VERIFY & RETRY                               │
│                                                                     │
│  Check: every source chunk → has output_chunk                      │
│         no empty/blank output files                                 │
│         manifest hashes match                                       │
│                                                                     │
│  Retry missing chunks (max 2 attempts)                              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 6: TRANSLATE BOOK TITLE                         │
│                                                                     │
│  Read original_title from config.txt                                │
│  Wrap in 书名号 for Chinese: 《translated_title》                   │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 7: MERGE & BUILD OUTPUTS                        │
│                                                                     │
│  merge_and_build.py →                                               │
│    • output.md          (merged translated Markdown)                │
│    • book.html          (web version with floating TOC)            │
│    • book_doc.html      (ebook version)                            │
│    • book.docx          (Word document)                            │
│    • book.epub          (e-book)                                   │
│    • book.pdf           (print-ready PDF)                          │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│               PHASE 8: REPORT                                       │
│                                                                     │
│  Summary: chunks translated, output files with sizes,               │
│           any format failures                                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Isolated Context per Chunk

Each sub-agent translates exactly **one chunk** (~6000 chars) in a completely fresh context window. The naive approach — feeding a whole book into a single LLM session — inevitably degrades quality: the model's attention dilutes across hundreds of pages, the middle chapters suffer, and output truncation becomes likely.

By contrast, this pipeline gives every fragment of the book the **same ideal conditions** as the first page. No context decay, no accumulated noise, no truncation. The model can focus 100% of its capacity on a single coherent passage.

### 2. Glossary-Driven Term Consistency (The Secret Weapon)

This is the single biggest quality driver. Without a shared glossary, the same entity drifts across chunks:
- `Sherlock Holmes` → chunk 1: *Шерлок Холмс*, chunk 2: *Шерлок*, chunk 3: *мистер Холмс*
- `Baker Street` → chunk 1: *Бейкер-стрит*, chunk 5: *улица Бейкер*

The pipeline solves this with a **canonical glossary** that every sub-agent must obey:

1. **Before translation**: sample the book, extract proper nouns and domain terms, build `glossary.json`
2. **Per-chunk injection**: each sub-agent receives only the terms relevant to its chunk (via `glossary.py print-terms-for-chunk`)
3. **Post-batch merge**: sub-agents emit `meta.json` files with proposed new entities. `merge_meta.py` auto-applies unanimous proposals and surfaces conflicts for main-agent resolution
4. **Progressive enrichment**: terms discovered in later chunks propagate back to earlier chunks on re-translation

The result: a character introduced in chapter 10 is translated identically when mentioned in chapter 2 on the next run. Over a full book, this eliminates the most visible class of translation inconsistency.

### 3. Neighbor Context for Cohesion

A chunk translated in isolation loses continuity: pronouns lose their referents, cross-chapter entities feel disconnected. Each sub-agent receives **read-only excerpts** (~300 chars) from the immediately preceding and following chunks.

This is strictly read-only — the sub-agent must not translate or copy these excerpts. They exist only for pronoun resolution, gender agreement, and entity tracking across chunk boundaries.

Without this, every chunk boundary would produce a noticeable seam. With it, the reader cannot tell where one chunk ended and the next began.

### 4. Language-Specific Translation Prompts

Generic "translate to Russian" prompts produce mediocre results because they lack language-specific typographic rules. This skill carries **dedicated prompts** for each supported language:

| Language | Prompt features |
|----------|----------------|
| Chinese (zh) | 书名号 `《》` for titles, CJK spacing rules, Chinese punctuation |
| Russian (ru) | «кавычки-ёлочки», em-dash rules, тире vs дефис, proper noun inflection |

Each prompt is battle-tested against real translation pitfalls: HTML-safe attribute escaping (`alt="Книга «Война и мир»"`), heading hierarchy detection, markdown structure preservation. Adding a new language means creating a new prompt with its own typographic rules.

### 5. Hash-Based Integrity Verification

Before any merge, the pipeline verifies:
- Every source chunk has a corresponding translated output
- Source chunk SHA-256 hashes match the manifest (no corruption during translation)
- No output files are empty or blank

This prevents the most frustrating class of bug: a book assembled with silently missing or corrupted chapters. If validation fails, only the affected chunks need re-translation.

### 6. Resumable at Chunk Granularity

Translation of a 300-page book can take hours. If the process is interrupted — network failure, API timeout, computer restart — the pipeline **resumes from where it stopped**, not from the beginning. Already-translated chunks are detected by the presence of valid `output_chunk*.md` files and skipped. `run_state.json` tracks per-chunk status for selective re-translation when the glossary changes.

This makes the skill practical for real use: you can start a large translation, walk away, come back, and continue without losing progress.

### 7. Multiple Output Formats from One Pipeline

The same translated chunks feed **five output formats** simultaneously:
- **HTML** — web-ready with floating table of contents
- **DOCX** — Microsoft Word, editable
- **EPUB** — standard e-book format
- **PDF** — print-ready

This is not a afterthought: `merge_and_build.py` produces all five from the merged `output.md` in a single pass.

### 8. Calibre-Mediated Input Normalization

PDF, DOCX, and EPUB are wildly different formats. Rather than writing separate parsers for each, the pipeline delegates to **Calibre's `ebook-convert`**, which normalizes any input → HTMLZ → HTML → Markdown. This means:
- One conversion script handles all input formats
- Edge cases (DRM-free PDFs with complex layouts, legacy EPUB2, DOCX with tracked changes) are handled by Calibre's mature codebase
- Adding a new input format requires zero pipeline changes — if Calibre supports it, the pipeline does too

### Why This Architecture Produces Better Translations Than Single-Session Approaches

| Factor | Single-session translation | Chunked pipeline with glossary |
|--------|---------------------------|-------------------------------|
| Context window | Entire book → attention decay | One chunk → full attention |
| Term consistency | Drifts over 50+ pages | Forced canonical via glossary |
| Recovery on failure | Start over from page 1 | Resume from last chunk |
| Parallelism | Sequential | 8+ concurrent sub-agents |
| Output quality | Degrades after ~20 pages | Consistent across 200+ pages |
| Format support | Usually plain text only | HTML + DOCX + EPUB + PDF |

The architecture was designed specifically to eliminate the weaknesses of naive LLM book translation: context overflow, term drift, irrecoverable interruptions, and single-format output.

## Directory Structure

```
translate-book-parallel/
├── SKILL.md                    # Hermes skill definition (orchestrator)
├── AGENTS.md                   # Agent development guide
├── ARCHITECTURE.md             # This file
├── CHANGELOG.md                # Version history
├── README.md                   # English user guide
├── README.ru.md                # Russian user guide
├── scripts/
│   ├── convert.py              # PDF/DOCX/EPUB → Markdown chunks
│   ├── manifest.py             # SHA-256 chunk tracking
│   ├── glossary.py             # Term-consistency glossary
│   ├── chunk_context.py        # Neighboring chunk excerpts
│   ├── meta.py                 # Sub-agent observation schema
│   ├── merge_meta.py           # Glossary merge from sub-agent feedback
│   ├── run_state.py            # Selective re-translation planner
│   ├── merge_and_build.py      # Merge → HTML → DOCX/EPUB/PDF
│   ├── calibre_html_publish.py # Calibre format wrapper
│   ├── template.html           # Web HTML template with TOC
│   └── template_ebook.html     # Ebook HTML template
├── tests/
│   ├── baselines/              # Test EPUB files
│   │   ├── standard-alice/
│   │   ├── sleepy-hollow/
│   │   └── diligent-dick/
│   └── test_*.py               # Unit tests (226 total)
└── LICENSE
```
