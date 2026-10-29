# Changelog

## v1.2.12 — CI: pinned dependencies, working cache key, ruff gate, Python 3.14 (2026-10-29)

- **Added** `requirements.txt` (T-02): `pypandoc==1.17` and `beautifulsoup4==4.15.0`, the versions the repository is actually verified with. `markdown` is documented as an optional accelerator (the tested path is the `_mab_html.py` regex fallback) and deliberately not a dependency
- **Fixed** `.github/workflows/ci.yml` (T-02): `cache-dependency-path` pointed at `scripts/setup.py`, which contains no dependency list — the pip cache could never be invalidated by a dependency change. Both jobs now key on `requirements.txt` and install from it instead of unpinned `pip install pypandoc beautifulsoup4`
- **Added** a `lint` job with `ruff==0.16.4` and a scoped `ruff.toml`: correctness-only checks (`E9` syntax errors, `F63` print-star, `F7` annotated-name syntax, `F82` undefined names) that unit tests can miss. Style rules stay out of scope — the codebase carries ~148 style remarks by design (audit §8.3); verified locally that the gate passes on the current tree
- **Added** Python 3.14 to the test matrix: the supported toolchain (scripts/setup.py) runs 3.14 locally, but CI never tested it
- **Fixed** `scripts/translate-launcher.bat` installing unpinned `pypandoc beautifulsoup4`; it now installs `-r %REPO_DIR%\requirements.txt`, so the launcher, CI and local docs share one dependency set
- **Verified**: `ruff check .` passes (exit 0); `pip install --dry-run -r requirements.txt` resolves; workflow YAML parses (3 jobs: lint, test, integration); suite stays 352 OK

## v1.2.11 — Documentation matches the pipeline: chunk size, formats, baselines, batch semantics (2026-10-28)

- **Fixed** `ARCHITECTURE.md` (D-01): the diagram and Phase-4 text claimed chunks of ~6000 chars — the v1.1 default; the actual default is 15000 (`--chunk-size`), now stated in both places. "The same translated chunks feed **five** output formats" listed only four; it now says four and explains that `book_doc.html` is the pandoc intermediate Calibre renders into DOCX/EPUB/PDF, and that `merge_and_build.py` exits non-zero if any format fails. "Adding a new input format requires zero pipeline changes" was also false: the extension allowlist in `convert.py` (`['.pdf', '.docx', '.epub']`) is a real one-line change (and the example name `leanbook-convert` was a typo for `ebook-convert`)
- **Fixed** `README.md`, `README.ru.md`, `README.zh-CN.md` (D-02): all three diagrams/texts said ~6000-char chunks; now ~15000, with the Chinese README naming `--chunk-size 15000` explicitly
- **Fixed** `tests/baselines/*` (D-03): metrics recorded under `target_size=6000`/concurrency 8 were listed as if current. Fresh conversion-only measurements (2026-10-28) recorded: sleepy-hollow **7** chunks, standard-alice **13** at the 15000 default / **31** at `--chunk-size 6000`, diligent-dick **8** / **16** at 6000. Historical v1.2.0-era counts (~21/~38/~57) are kept and explicitly labeled with the configuration that measured them; `baselines/README.md` now states explicitly which numbers belong to which configuration and that they must not be compared across chunker versions or defaults. The alias-stress rationale now cites the measured Dick/Richard/Stuart co-occurrence (chunks 1–6 of 8 at the default, 2–12 of 16 at 6000) instead of never-verified guesses, and sleepy-hollow `SOURCE.md` records the real smoke run (7 chunks; DOCX/EPUB/PDF OK with real Calibre 9.11 after the v1.2.8 SVG fix)
- **Documented** in `standard-alice/SOURCE.md`: `manifest.source_hash` is the SHA-256 of the generated `input.md`, **not** of the epub; the epub identity is `sha256 d708184c72ccb1848e10e0b456e2ec145c67a3b93ba562fc528cfa07754e5140` (10 635 439 bytes, byte-identical to git blob `95f8c238` at `cde660b`)
- **Fixed** `SKILL.md` (D-04): §4 said "each batch: up to `concurrency` sub-agents in parallel (default: 24)" while also capping at 3 per `delegate_task` call. `concurrency` is the batch size in chunks; a 24-chunk batch ships as 8 `delegate_task` calls carrying 3 tasks each (same clarification at the parameter list). §8's example claimed final files land in `test-output/`; `merge_and_build.py` writes them inside the temp dir (`All outputs saved to: {temp_dir}`) and only the Windows launcher moves them to `translations/`
- **Tests**: no new tests — docs-only batch; suite stays at 352 OK, including `test_skill_md.py` guarding the Russian prompt block

## v1.2.10 — Launcher, shortcut script and chunk-size defaults match the pipeline again (2026-10-28)

- **Fixed** `scripts/translate-launcher.bat` (C-10): it advertised TXT support and offered `*.txt` in the file picker, but `convert.py` rejects `.txt` with exit 1; the format check now compares `.epub`/`.pdf`/`.docx` exactly instead of `findstr` over a free-text list. `pip install` became `python -m pip install` so the packages land in the interpreter that runs the pipeline. Dependencies are still installed before the conversion, but into the right environment
- **Fixed** the launcher passing `--title "%BOOK_NAME%"`, which overwrote the book's metadata title with the file name. `merge_and_build.py` now resolves the title as `--title` → `original_title` from `config.txt` (written by `convert.py`) → input file name → `"Translated Book"`, and the launcher simply omits `--title`
- **Fixed** the launcher moving results only when `book.epub` exists: a failed EPUB used to hide a good DOCX/PDF. Each format is moved independently, and the exit-1 message now says the build failed either because translations are missing or because a format conversion failed (not "translation may not be complete yet" for every failure)
- **Fixed** the launcher banner claiming `v1.0` while the project is at 1.2.x; the banner no longer hardcodes a version
- **Fixed** `scripts/create-desktop-shortcut.ps1` (C-11): `` `u{2705} `` needs PowerShell 6+ and prints literally under Windows PowerShell 5.1 (the usual interpreter for `.ps1`). Uses `[char]::ConvertFromUtf32(0x2705)` now; the description no longer claims TXT
- **Fixed** `convert.py` (C-12): `merge_blocks_to_chunks()`, `split_markdown_text()` and `split_markdown_structured()` defaulted to `target_size=6000` while the CLI default is 15000, so calling them from Python produced 2.5× more chunks than the same book through the CLI. All of them and the CLI now share `DEFAULT_CHUNK_SIZE = 15000`
- **Tests**: 337 → 352. `test_launcher_scripts.py` checks the `.bat`/`.ps1` against the pipeline (no TXT, `python -m pip`, no `--title` override, per-format moves, PowerShell 5 escape); `ChunkSizeDefaultTests` pins the library and CLI defaults to one constant; `ResolveTitleTests` pins the title precedence
- **Verified**: the launcher rejects a `.txt` file with `Format .txt not supported. Supported: EPUB, PDF, DOCX` and exit 1; a build without `--title` on the sleepy-hollow baseline prints `Title: The Legend of Sleepy Hollow` from `config.txt`; `create-desktop-shortcut.ps1` parses cleanly under Windows PowerShell 5.1

## v1.2.9 — `--cleanup` no longer destroys the translations (2026-10-28)

- **Fixed** `merge_and_build.py` (C-09): `--cleanup` deleted `chunk*.md` **and** `output_chunk*.md`, so after a successful build the book could not be rebuilt at all — `validate_for_merge` needs the output chunks, and changing the title, font, cover or export name then required translating the whole book again. `translate-launcher.bat` always passes `--cleanup`, so launcher users hit this on every build
- **Behaviour**: `--cleanup` now removes only the rebuildable intermediates (`input.html`, `input.md`, `output.html`) and keeps the chunks/translations, printing what it removed and what it kept. Deleting the translations is a separate, explicit `--cleanup-translations` (requires `--cleanup`), and it states that a rebuild will need a retranslation. The deletion plan is printed before anything is removed
- **SKILL.md**: §7 documents the new split; the `--cleanup` example stays valid and is now non-destructive
- **Tests**: 333 → 337, new `CleanupIntermediateFilesTests`: default cleanup keeps `chunk*.md`/`output_chunk*.md` and the final formats, `--cleanup-translations` deletes them, the output names what is removed/kept, and `--cleanup-translations` without `--cleanup` exits 2
- **Verified on a real 7-chunk book with Calibre 9.11**: build with `--cleanup` exits 0, keeps 14 chunk files; a second build with a different `--title` succeeds and the new title appears in `book.html`; `--cleanup-translations` leaves only the final artifacts

## v1.2.8 — Calibre: SVG-wrapped illustrations no longer break DOCX and no longer vanish from EPUB/PDF (2026-10-28)

- **Fixed** `calibre_html_publish.py`: Calibre's HTMLZ extraction stores each bitmap illustration as `<img src="data:image/svg+xml;base64,…">` wrapping `<svg><image href="images/000000.jpg"/></svg>`. That wrapper survived the markdown round-trip and Calibre 9.11's DOCX writer abort with `AttributeError: 'NoneType' object has no attribute 'encode'` — the DOCX build failed and the whole build exited 1. Before rendering, `prepare_html_for_conversion()` now rewrites such an `<img>` to point at the bitmap it wraps (`src="images/000000.jpg"`), which keeps the picture and makes DOCX conversion succeed. Plain raster `data:` URIs, genuine vector SVGs without an inner bitmap, and unparseable payloads are left untouched
- **Impact beyond DOCX**: the wrapper also hid the illustration from EPUB and PDF — Calibre does not follow the `href` inside an SVG data URI. On the sleepy-hollow baseline `book.epub` grew from 70 KB to 336 KB and now contains `000000.jpg`, i.e. the picture is really embedded
- **Fixed**: a failed conversion left Calibre's truncated output on disk (`book.docx` at 42 KB of a 283 KB book), and the next build then reported "Skipping .docx — already exists and up to date". `convert_html_with_calibre()` now remembers the output's previous mtime/size and deletes the file only if this run changed it (a pre-existing file that Calibre never touched is kept)
- **Tests**: 325 → 333. `UnwrapSvgDataUriImagesTests` covers the base64 wrapper, `xlink:href` + single quotes, raster `data:` URIs, vector-only SVG, malformed base64 and the `prepare_html_for_conversion()` round-trip; two new `ConvertHtmlWithCalibreTests` pin the partial-output removal and the "don't delete an untouched previous output" case
- **Verified with real Calibre 9.11**: `SMOKE_FORMATS=1 tests/integration_smoke.py` now reports `.docx: OK (283,729 bytes), .epub: OK (336,753 bytes), .pdf: OK (539,195 bytes)`; before the fix DOCX failed with the traceback above

## v1.2.7 — `generate_formats()` returns a real bool on the empty-directory path (2026-10-28)

- **Fixed** `_mab_formats.py` (C-08): `generate_formats()` is declared to return `bool` and its callers key on it (`integration_smoke.py`, `merge_and_build.main()`), but the "no HTML files" branch ended with a bare `return`, i.e. `None`. Any future `is False` / `== False` check would silently misread that as success
- **Behaviour**: that branch now returns `False`, and the docstring states the contract (True only when every format was produced). `merge_and_build.main()` behaviour is unchanged — `None` and `False` were both falsy — but the cause now matches the message
- **Tests**: 322 → 325, new `GenerateFormatsReturnTests`: empty dir → `False` (and `isinstance(..., bool)`), all three formats succeeding → `True`, one failing → `False`

## v1.2.6 — `merge_meta.py`: readable error instead of a traceback when the glossary is missing (2026-10-28)

- **Fixed** `merge_meta.py` (C-07): `prepare-merge` and `apply-merge` call `load_glossary()`, which raises `FileNotFoundError` (and `ValueError` for unreadable JSON or a schema mismatch); `main()` did not catch either, so a missing `glossary.json` produced a raw Python traceback. SKILL.md §3.5 builds the glossary before translation, but the skill also allows working without one and the file can be deleted by hand — that is a user-fixable input problem, not a crash
- **Behaviour**: the error is printed as `error: Glossary not found: <path>` plus a `hint:` naming the next step (build it per SKILL.md §3.5 or use a temp dir that has one), exit code **2**; a malformed glossary prints `error: ...` and also exits 2. `status` keeps working without a glossary as before
- **Tests**: 318 → 322, new `CliGlossaryErrorTests` drives `main()` through `sys.argv`: missing glossary on `prepare-merge` / `apply-merge`, corrupt JSON, and `status` on an empty dir (must still succeed). Each asserts exit code, stderr text and the absence of `Traceback`

## v1.2.5 — SKILL.md: self-contradictory escaping example, Chinese leakage in the Russian prompt (2026-10-28)

- **Fixed** `SKILL.md` (C-06): the "correct" example for escaping quotes inside an `alt` attribute was byte-for-byte the example declared wrong on the line above, so the only place documenting attribute escaping gave the translator two opposite instructions. The correct line now shows `&quot;` and typographic quotes only; the straight inner quote appears exclusively in the wrong example
- **Fixed**: Chinese words had leaked into the Russian sub-agent prompt — `номера引用` → `номера ссылок`, `и跨 fragment ссылок` → `межфрагментных ссылок`. `SKILL.md` is an executable prompt (sub-agents receive these lines verbatim), not documentation
- **Tests**: 312 → 318, new `tests/test_skill_md.py`: the Russian prompt block is scanned for CJK characters (only that block — the Chinese prompts and Chinese glossary examples elsewhere are intentional), wrong and correct `alt` examples must differ, every correct example must parse back into exactly one `alt` attribute with `喝我` intact, and the wrong example must really carry the extra quotes that break the attribute. Negative control: 4 of the 6 fail against the pre-fix `SKILL.md`
- **Not changed**: the intentional Chinese examples elsewhere in the file (the `zh` prompt, glossary JSON samples) are legitimate and stay

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
