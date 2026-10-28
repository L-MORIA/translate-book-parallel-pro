# Changelog

## v1.2.4 — Security: HTML sanitizer now parses instead of pattern-matching (2026-10-28)

- **Fixed** `_mab_html.py` (C-04): `sanitize_html_body()` was a denylist of regexes over raw markup, so it only recognised quoted attribute values and only scheme-checked `href` on `<a>`. Unquoted `onerror=`, `<iframe src="javascript:">`, `<button formaction="javascript:">`, `<object data=…>`, `<meta http-equiv="refresh">` and entity-encoded schemes all reached `book.html`, which the user opens in a browser. The body is now parsed with the stdlib HTML parser and re-emitted: active elements (`script`, `iframe`, `object`, `embed`, `applet`, `frame`, `frameset`, `base`, `param`, `meta`, `link`) are dropped with their contents, every `on*` attribute and `srcdoc` is dropped, and URL attributes (`href`, `src`, `srcset`, `action`, `formaction`, `poster`, `cite`, `background`, `longdesc`, `usemap`, `data`, `dynsrc`, `lowsrc`, `xlink:href`) are checked on the value the browser would see — entities decoded, whitespace and control characters stripped. `style` attributes carrying `expression()`, `javascript:` or `data:text/html` are dropped
- **Security**: this closes the bypass class rather than the individual payloads. Because the tag is rebuilt from the parsed form, a quote or entity inside an attribute value can no longer break out of the attribute or hide a scheme. `data:image/*` stays allowed in image context (Calibre stores bitmap illustrations as base64 SVG wrappers — blocking it silently replaced real book images with `#`) and only raster types are allowed outside it
- **Fixed** while rewriting: inline SVG survives the round-trip — self-closing tags keep their slash (`<path/>` is not `<path>` in foreign content) and case-sensitive SVG names are restored (`viewBox`, `linearGradient`, `gradientUnits`, …), which HTML parsing lowercases but XHTML/EPUB consumers do not accept
- **Tests**: 296 → 310. `SanitizeHtmlBodyBypassTests` covers the four audit payloads plus entity-encoded and control-character schemes, `<object>`/`<embed>`/SVG `<script>`/`<meta refresh>`, `style` payloads and the `data:` URL policy; it also pins that escaped `<script>` text and `&amp;` entities in prose survive, and that attribute values are escaped when re-serialised
- **CI**: `integration_smoke.py`'s hostile payload now includes an unquoted handler, an iframe, a `formaction` and an entity-encoded scheme, and fails on any `pwned-*` marker or leftover `on*` handler / `javascript:` / `<iframe>`
- **Regression evidence**: on the sleepy-hollow baseline the generated 107 KB `book.html` is byte-identical to the previous output except the token order of CSS classes in five `<a>` tags — and pandoc's own pre-sanitizer `output.html` already has that order, so the sanitizer re-serialises the book without changing it

## v1.2.3 — Chunking: `--chunk-size` is a target again (2026-10-27)

- **Fixed** `convert.py` (C-03): every heading closed the current chunk unconditionally, so `--chunk-size` only ever acted as a ceiling. A book with a heading every ~500 characters became one tiny chunk per heading (10 sections × 520 chars at `--chunk-size 15000` → 10 chunks of 513), multiplying sub-agent count, cost and runtime while leaving each sub-agent with almost no context to translate coherently. A heading now closes a chunk only once that chunk is at least `HEADING_BREAK_FRACTION` (0.5) full, so short sections pack together and the size target is actually used. Measured on the sleepy-hollow baseline: 11 chunks → 7 (the minimum for a 90k-char book at 15000), the 135-char mid-book fragment is gone (sizes now 15010…13579 plus the 2317-char tail), `output.md` byte-identical (90,205 bytes)
- **Fixed** `convert.py`: refusal to reuse a chunk set now distinguishes two cases, because they need opposite advice. If the files still match the current split at their own numbers (interrupted split, manual deletion) the split is reproducible, so regenerating from `input.md` keeps chunk numbering and existing `output_chunk*.md` translations stay valid. If they do not match (different `--chunk-size`, older splitter) re-splitting moves every boundary; when translations exist the message now says so explicitly and recommends re-running with the original `--chunk-size` or starting a fresh temp directory — previously it just said "delete chunk*.md, translations are kept", which would have attached finished work to the wrong source text
- **Tests**: 291 → 296 (`merge_blocks_to_chunks` short-section packing, heading still breaks a half-full chunk, size stays an upper bound; reuse advice for a damaged own split vs a foreign split with translations). `integration_smoke.py` no longer asserts a hardcoded `>= 10 chunks` (it encoded the old per-heading behaviour) and now checks what matters: several chunks, chunk bytes within 2 % of `input.md`, and no chunk above 110 % of the 15000-char target
- **Compatibility**: temp dirs whose chunk boundaries coincide with the new splitter keep working unchanged (verified on a real 13-chunk dir with 5 finished translations); a dir that no longer matches is refused with a migration hint instead of silently renumbering translations

## v1.2.2 — Correctness: chunk-set validation, HTML rebuild stamp, manifest robustness (2026-10-27)

- **Fixed** `convert.py` (silent text loss): re-running convert.py on a partial chunk set rebuilt `manifest.json` from the surviving files and exited 0 — the book shipped with chapters missing. Reuse is now gated on the chunk set being a complete, unmodified split of `input.md`: contiguous `chunkNNNN.md` numbering, no empty files, total size within ±10 % of `input.md`, and byte-identical comparison against a fresh in-memory split at the current `--chunk-size`. Any mismatch aborts with exit 1 and a fix hint instead of rebuilding (`output_chunk*.md` translations are preserved)
- **Fixed** `_mab_html.py` (stale/missing HTML): HTML regeneration was decided by the mtime of `book_doc.html` alone, so a missing `book.html`, a changed `--title`/`--author`/`--olang`, or an edited template silently kept the old output. The skip decision now uses `.html_build_stamp.json` (sha256 of `output.md` + title/author/lang + template mtimes) and requires both `book_doc.html` and `book.html` to exist and pass the image sanity check; failures to write either file now return False instead of being ignored
- **Fixed** `manifest.py` (integrity gate): a truncated `manifest.json` raised `JSONDecodeError` and a manifest without a `chunks` key raised `KeyError` inside `validate_for_merge`. Both now raise `ManifestError`, are reported as `ERROR: …` with a rebuild hint, and **block** the merge — a corrupt manifest no longer falls back to the legacy glob merge that would skip the hash gate. A *missing* manifest still uses legacy mode. `create_manifest` writes atomically (`mkstemp` + `os.replace`)
- **Fixed** `convert.py`: chunk filenames are sorted numerically, not lexicographically (`chunk10000.md` no longer sorts before `chunk1001.md`, which would corrupt manifest order past 9999 chunks)
- **Internal**: `split_markdown_text()` extracted so the splitter and the reuse check share one implementation
- **Tests**: 271 → 291. New: `ChunkSetReuseTests` (deleted / truncated / gap / wrong `--chunk-size` / foreign `chunk*.md` / missing `input.md`), `ManifestRobustnessTests` (corrupt JSON, missing `chunks`, malformed entry, legacy fallback, no temp leftovers), `HtmlBuildStampTests` (both outputs, missing `book.html`, title/author/lang/`output.md` changes, unchanged inputs still skip)

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
