# Changelog

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

- `ebook-convert` from Calibre 7.0.0 (already installed)
- `pandoc` 3.10 (winget install)
- `pypandoc` (pip install — added to Hermes venv)
- `beautifulsoup4` 4.15.0 (already installed)

### Adaptations for Hermes

- `delegate_task` max 3 concurrent sub-agents per batch (configurable via `delegation.max_concurrent_children`)
- All script paths use `{baseDir}` for skill-relative resolution
- Translation prompt unchanged — same quality rules, term table, and neighbor context

## v1.1.0 — Memory Fix & Sherlock Holmes Smoke Test

### Memory Overflow Incident (2026-07-05)

**Symptoms:** Running 3 parallel sub-agents (concurrency=3) on an 8GB RAM system caused Hermes to crash with memory overflow after translating 8 chunks.

**Root cause:** Each sub-agent loads the LLM independently. 3 concurrent × ~10KB context per chunk × accumulation in parent conversation = RAM exhaustion on 8GB systems.

**Fix applied:**
- Added `check_ram()` to `scripts/setup.py` — warns if <8GB RAM detected
- Added `Memory & Performance Notes` section to `SKILL.md` — recommends concurrency=1 on low-RAM systems
- Default concurrency reduced to 1 for Hermes Agent (memory-safe mode)
- Resumable pipeline design confirmed: crash only loses in-flight chunks, completed chunks survive

### Added
- `tests/smoke_test.md` — sample English book page (Sherlock Holmes)
- `tests/output_sample.md` — actual Russian translation output from the smoke test
- `scripts/setup.py` — RAM check: detects physical RAM, warns if below 8GB threshold

### Changed
- `SKILL.md` — added Memory & Performance Notes section
- `scripts/setup.py` — integrated `check_ram()` into verification pipeline
