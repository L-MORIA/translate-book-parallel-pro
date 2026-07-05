# Test Results

**Suite:** 226 unit tests
**Environment:** Windows 10, Python 3.11.9, Calibre 7.0.0, Pandoc 3.10
**Date:** 2026-07-05
**Result:** ✅ All 226 passed (2.85s)

## By Module

| Module | Tests | Status |
|--------|------:|--------|
| `test_convert` | 18 | ✅ |
| `test_manifest` | 6 | ✅ |
| `test_glossary` | 38 | ✅ |
| `test_chunk_context` | 4 | ✅ |
| `test_meta` | 8 | ✅ |
| `test_merge_meta` | 76 | ✅ |
| `test_run_state` | 13 | ✅ |
| `test_merge_and_build` | 22 | ✅ |
| `test_calibre_html_publish` | 2 | ✅ |
| *(from `test_merge_meta` — alias, collision, chain tests)* | 39 | ✅ |

## Smoke Test (integration)

**Input:** `sleepy-hollow.epub` (287 KB, Washington Irving)
**Pipeline stage:** `convert.py`
**Result:** ✅ 21 chunks created, manifest + config generated

## Coverage Areas

- **Convert pipeline** — Calibre HTMLZ → Markdown, chunk splitting, fingerprinting, cache validation, page number stripping, CJK handling
- **Manifest validation** — SHA-256 integrity, empty/missing/undecodable output detection
- **Glossary** — v1→v2 upgrade, term consistency, per-chunk term table, frequency counting, CJK boundary matching, atomic write
- **Chunk context** — neighbor excerpts, edge chunks, prompt formatting
- **Sub-agent meta** — schema validation, atomic write, hash stability, chunk ID extraction
- **Meta merge** — auto-apply new entities, alias resolution, conflict resolution, confidence promotion, multi-variant collisions, chain resolution, resume contract, status reporting
- **Run state** — selective re-translation planning, glossary-edit tracking, resume tracking, blank/missing output detection
- **Merge and build** — HTML image validation (escaped quotes, missing src, broken markdown), multi-format output (HTML/DOCX/EPUB/PDF), export naming, cover image, incremental rebuild
- **Calibre publish** — EPUB/DOCX/PDF command construction, cover argument passthrough
