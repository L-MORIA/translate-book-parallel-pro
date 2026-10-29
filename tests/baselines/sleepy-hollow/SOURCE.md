# sleepy-hollow

Smoke baseline — cheapest full-pipeline input that still exercises convert, chunking, glossary, merge, and final format generation.

- File: `sleepy-hollow.epub`
- Source: Project Gutenberg #41 *The Legend of Sleepy Hollow* (`epub3.images`)
- Why this baseline: with the current default (`--chunk-size 15000`) it splits into **7 measured chunks**, enough to exercise cross-chunk alias tracking: the `Headless Horseman / Galloping Hessian / spectre / goblin` alias chain spans several of them, so cross-chunk entity tracking still gets exercised. (Historical note: under the v1.2.0 chunker at the 6000 default the same input split into ~21 chunks; the v1.2.3 heading-aware splitter changed that, and the current default is 15000 — any of these numbers describes only the configuration that measured it.)
- Coverage gap: only 1 image (the cover) — does **not** exercise inline-image preservation. Use `standard-alice` for image-path coverage.

Run from `tests/.artifacts/` so generated files stay out of the repo root:

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python ../../scripts/convert.py ../baselines/sleepy-hollow/sleepy-hollow.epub --olang zh
# then run translation via the skill
python ../../scripts/merge_and_build.py --temp-dir sleepy-hollow_temp --title "睡谷传奇（Smoke Baseline）"
```

## Expected outcome

See `tests/baselines/README.md` for the three-tier convention.

*Forward-looking targets, not yet validated. The first full pipeline run after this section was added is the validation event — promote items to **Measured** as a run confirms them, or correct the targets if the run reveals the spec was wrong.*

### Measured (integration smoke, real Calibre run of 2026-10-28)

The pipeline under its current defaults (`--chunk-size 15000`) splits this
baseline into exactly **7 chunks** on every real run. Note that
`tests/integration_smoke.py` asserts chunk *properties* (≥2 chunks, lossless
±2% byte conservation, no chunk over 110% of 15000 chars, manifest count
equality) — the exact `7` is noise-stable but not gated in CI.

- `manifest.chunk_count == 7`, chunk files `chunk0001.md`–`chunk0007.md`
- All 4 final formats generated with real Calibre 9.11:
  `book.docx` OK, `book.epub` OK, `book.pdf` OK (this requires the
  SVG-wrapped-illustration fix from v1.2.8; before it, DOCX always failed)
- The cover image is preserved end-to-end into the final outputs
  (`000000.jpg` shows up inside `book.epub`/`book.docx`)

### Expected target (unverified — needs a full pipeline run with real translation)

- `manifest.chunk_count` is 7 (see **Measured**). First run with a different code version records the exact value; subsequent runs assert equality against the recorded value, not against `7`
- All `chunk*.md` and matching `output_chunk*.md` exist; count matches `manifest.chunk_count`
- 1 image (cover) preserved end-to-end into the final EPUB
- All 4 final formats generated: `book.html`, `book.docx`, `book.epub`, `book.pdf`
- Glossary entries for `Ichabod Crane`, `Headless Horseman`, `Brom Bones`, `Katrina Van Tassel` reach `confidence == "high"` (≥3 evidence_refs each, per `scripts/merge_meta.py:76-91`)
- **Primary assertion** (the reason this baseline exists beyond smoke coverage): `Headless Horseman` and `Galloping Hessian` resolve to a *single* glossary entity, with both surface forms present in `aliases`. If they split into two entities, the cross-chunk alias coverage failed.

### Drift indicator (record current values, do not pass/fail)

- `Ichabod Crane.target`: a single Chinese form across all chunks (consistency only, not a specific value)
- `Brom Bones`'s alias chain (`Abraham`, `Brom Van Brunt`) collapses into one entity
