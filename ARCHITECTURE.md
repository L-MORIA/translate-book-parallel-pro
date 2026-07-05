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
Each sub-agent starts fresh. Prevents context overflow on long books.

### 2. Hash-Based Integrity
SHA-256 tracking catches stale/corrupt chunks before merging.

### 3. Resumable at Chunk Granularity
Re-run the skill — already-translated chunks are skipped automatically.

### 4. Format-Agnostic Input
Calibre normalizes PDF/DOCX/EPUB → HTMLZ → Markdown before pipeline begins.

### 5. Multiple Output Formats
Single pipeline produces HTML, DOCX, EPUB, and PDF simultaneously.

### 6. Glossary-Driven Consistency
Shared glossary prevents term drift across parallel sub-agents.

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
