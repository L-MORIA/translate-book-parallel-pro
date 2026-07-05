# AGENTS.md

## Project

**translate-book-parallel** is a Hermes Agent Skill that translates books (PDF/DOCX/EPUB) into any language using parallel sub-agents (`delegate_task`). Ported from `deusyu/translate-book` (Rainman Translate Book), originally a Codex/Claude Code skill.

## Structure

- `SKILL.md` — Skill definition, the orchestration logic that Hermes follows
- `scripts/convert.py` — PDF/DOCX/EPUB → Markdown chunks (via Calibre HTMLZ)
- `scripts/manifest.py` — SHA-256 chunk tracking and merge validation
- `scripts/glossary.py` — Term-consistency glossary; per-chunk term tables injected into sub-agent prompts
- `scripts/chunk_context.py` — Read-only previous/next chunk excerpts injected into sub-agent prompts
- `scripts/meta.py` — Per-chunk sub-agent observation file schema
- `scripts/merge_meta.py` — Batch-boundary merge of sub-agent observations into the canonical glossary
- `scripts/run_state.py` — Selective re-translation planner and run_state.json recorder
- `scripts/merge_and_build.py` — Merge translated chunks → HTML → DOCX/EPUB/PDF
- `scripts/calibre_html_publish.py` — Calibre format conversion wrapper
- `scripts/template.html`, `scripts/template_ebook.html` — HTML templates

## Hermes-specific adaptations

- Sub-agent tool: `delegate_task` (not Claude Code `Agent`)
- Python: `python` (not `python3`) — Hermes venv compatibility
- All script invocations use `python` not `python3`
- Shebangs: `#!/usr/bin/env python` not `#!/usr/bin/env python3`
- Max 3 concurrent sub-agents by default (configurable via `delegation.max_concurrent_children` in `config.yaml`)

## Testing changes

Use a small EPUB for quick checks, or the checked-in baseline book.

Quick smoke test:

```bash
python scripts/convert.py /path/to/small.epub --olang zh
# then run translation via the skill in Hermes
python scripts/merge_and_build.py --temp-dir <name>_temp --title "test"
```

Full baseline test:

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python ../../scripts/convert.py ../baselines/standard-alice/standard-alice.epub --olang zh
# Create mock output_chunk*.md files (copy source chunks)
for f in standard-alice_temp/chunk*.md; do cp "$f" "standard-alice_temp/output_$(basename $f)"; done
python ../../scripts/merge_and_build.py --temp-dir standard-alice_temp --title "test"
```

Verify: all output_chunk*.md files exist, manifest validation passes, output formats generate.

Unit tests:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Conventions

- Only `chunk*.md` naming — no `page*` legacy support
- SKILL.md frontmatter must stay single-line per field (Hermes parser requirement)
- Script paths in SKILL.md use `{baseDir}` not hardcoded paths
- Sub-agent instructions in SKILL.md must be platform-neutral (work on Hermes, Codex, OpenClaw)
- Checked-in baseline inputs live under `tests/baselines/<book-id>/`; generated full-pipeline outputs live under `tests/.artifacts/`
- Releases: `git push origin main && git tag vX.Y.Z && git push --tags`

## Do not

- Do not reintroduce `page*` file support — it was intentionally removed
- Do not hardcode paths in SKILL.md — use `{baseDir}`
- Do not put `python3` in scripts or documentation — use `python`
- Do not add mtime-based incremental rebuild for HTML/format generation — the current skip logic is intentionally simple (existence check). Metadata/template changes require manual cleanup.

## Known issues (Windows-specific)

- Calibre installs `ebook-convert.exe` to `C:\Program Files\Calibre2\` — ensure it's in PATH
- `python` in git-bash may point to Hermes venv (`.../hermes-agent/venv/Scripts/python`) — install pypandoc there or use system Python directly
- Pandoc installs to `C:\Users\<user>\AppData\Local\Pandoc\` — ensure it's in PATH
- Unit tests pass from repo root (`python -m unittest discover -s tests -p 'test_*.py'`) — run from `D:\translate-book-skill\` or the skills directory with proper `PYTHONPATH`
