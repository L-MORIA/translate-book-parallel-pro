# Changelog

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
