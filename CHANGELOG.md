# Changelog

## v1.2.1 — Full audit: security, correctness, tests, repo hygiene (2026-10-25)

- **Fixed** `convert.py`: the `[**bold**]` cleaner no longer corrupts real markdown links (`[**Chapter 1**](url)` stayed intact now)
- **Fixed** `merge_and_build.py`: exits 1 when output format generation fails (previously exit 0 → launcher reported success on failed builds)
- **Security**: HTML escaping for title/author from source-book metadata; TOC anchor text escaped; `sanitize_html_body()` strips `<script>` blocks, `on*` event handlers and `javascript:` URLs from generated `book.html`
- **Fixed** `_mab_toc.py` regex fallback: heading text no longer passed through `re.sub` replacement strings (`\g` crashed the build); attributed headings (`<h2 class=…>`) now get TOC ids; pre-existing pandoc ids are reused instead of duplicated
- **Fixed** `glossary.py`: word-boundary matching now applies to non-ASCII sources (Cyrillic/Greek/umlauts) — frequencies and per-chunk term injection no longer over-match inside larger words
- **Fixed** Windows encoding: all `subprocess` captures decode UTF-8 with `errors='replace'`; `setup.py` status output is ASCII (emoji crashed piped runs under cp1251/cp866)
- **Tests**: 226 → 270. New coverage: `_mab_toc` (was zero), convert chunker (`parse_structural_blocks` / `merge_blocks_to_chunks` / `_force_split_block` / `split_markdown_structured`), manifest merge-time integrity gate (hash mismatch / missing source / short output), `sanitize_html_body` + template escaping
- **CI**: actions pinned by SHA; Python matrix 3.9–3.13; unit-test matrix no longer installs Calibre (everything is mocked); new `integration` job runs the real pipeline (Calibre → chunks → manifest → simulated translation → merge → HTML → TOC) on the sleepy-hollow baseline via `tests/integration_smoke.py`
- **Repo hygiene**: removed orphan `hermes-time-machine-test-v2.epub`; 11 MB `standard-alice.epub` fixture untracked (fetch on demand per its `SOURCE.md` — file remains on disk for existing checkouts)
- **Docs**: install URLs point to `translate-book-parallel-pro`; README Python floor 3.9+ (3.8 is EOL, never tested in CI); `CLAUDE.md` now defers to `AGENTS.md` (was a stale copy describing the pre-fork project); concurrency defaults unified (skill batch default 24, Hermes-side `delegate_task` cap 3); zh-CN README banner notes it describes the original Claude Code skill

## v1.2.0 — Refactoring: merge_and_build.py decomposition (2026-07-12)

- **Refactored**: `scripts/merge_and_build.py` split from monolithic 1027-line file into a thin orchestrator + 6 domain-specific `_mab_*` modules:
  - `_mab_common.py` — language config, config.txt loader, natural sort
  - `_mab_images.py` — image reference validation and HTML sanity checks
  - `_mab_merge.py` — chunk merging into output.md
  - `_mab_html.py` — Markdown→HTML conversion chain (pandoc → py-markdown → regex)
  - `_mab_toc.py` — table of contents generation (BS4 → regex)
  - `_mab_formats.py` — DOCX/EPUB/PDF generation and export aliases
- **Zero behavior change**: all 26 existing tests pass unchanged; public API surface re-exported from `merge_and_build` for mock compatibility
- **New `--cleanup` flag**: optional removal of intermediate artifacts (chunks, input.html) after successful build (already documented in SKILL.md)

## v1.1.1 — Calibre ≥ 9.x requirement

- **Discovered**: Calibre 7.0.0 causes timeouts in `merge_and_build` (`ebook-convert` hangs on PDF/EPUB generation via subprocess)
- **Fix**: minimum Calibre version raised to 9.x
- **Detection**: `winget upgrade calibre.calibre` upgrades to the latest (9.11.0+)
- **Full pipeline test**: Sherlock Holmes (111 chunks, 589KB) → HTML/DOCX/EPUB/PDF generated successfully in <3 min on Calibre 9.11.0

## v1.1.0 — Memory fix, RAM check, Sherlock Holmes smoke test

- `setup.py`: RAM check before benchmark, Sherlock Holmes smoke test
- `tests/smoke_test.md`: sample excerpt from "A Scandal in Bohemia"
- `tests/output_sample.md`: Russian translation sample with pipeline metadata

## v1.0.0 — Hermes Agent Port

Original: `deusyu/translate-book` (Rainman Translate Book)
Port: `translate-book-parallel` (Hermes Agent)

### What changed

- **Platform**: ported from Claude Code / Codex Skill → Hermes Agent Skill
- **Sub-agent mechanism**: replaced `Agent` tool with `delegate_task` (Hermes parallel sub-agent API)
- **Allowed tools**: `Read, Write, Edit, Bash, Glob, Grep, Agent, AskUserQuestion` → `Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, execute_code`
- **Python invocation**: all `python3` references replaced with `python` (Hermes venv compatibility)
- **Shebangs**: `#!/usr/bin/env python3` → `#!/usr/bin/env python` in all 9 scripts
- **Metadata**: `openclaw` → `hermes` in SKILL.md frontmatter
- **Name**: `translate-book` → `translate-book-parallel`

### Dependencies (Windows)

- `ebook-convert` from Calibre ≥ 9.x (upgrade via `winget upgrade calibre.calibre`)
- `pandoc` 3.10 (winget install)
- `pypandoc` (pip install — added to Hermes venv)
- `beautifulsoup4` 4.15.0 (already installed)

### Adaptations for Hermes

- `delegate_task` max 3 concurrent sub-agents per batch (configurable via `delegation.max_concurrent_children`)
- All script paths use `{baseDir}` for skill-relative resolution
- Translation prompt unchanged — same quality rules, term table, and neighbor context
