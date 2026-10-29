# diligent-dick

Opt-in alias-stress baseline — exercises the `merge_meta` contested-variant and alias-chain paths under realistic cross-chunk pressure. **Not part of default CI.** Run when changing `scripts/merge_meta.py` or `scripts/glossary.py`.

- File: `diligent-dick.epub`
- Source: Project Gutenberg #71493 *Diligent Dick; or, The Young Farmer* (`epub3.images`)
- Why this baseline: the protagonist appears as `Dick` / `Richard` / `Stuart` (with `Mr. Stuart` ambiguating father vs. son), and the three variants co-occur under sustained cross-chunk pressure. With the current chunker (v1.2.3+) Dick and Richard share chunks 1–6 of 8 at the default size (measured 2026-10-28); under the historical 6000-config they shared chunks 2–12 of 16. The alias pressure is therefore almost continuous rather than confined to one batch — exactly what the `merge_meta` "Surface ALL competing proposals" / "Surface ALL alias candidates" fixes are meant to protect.
- Cost note: 8 chunks at the default size, 16 at `--chunk-size 6000`; real story content spreads over all of them. (Historical: the v1.2.0 chunker cut this book's many short Sunday-school chapters into ~57 pieces, ~30 of them tiny heading- or image-only chunks; the v1.2.3 heading-boundary change removed that. Treat modern chunk counts as measured, not `~57`.)
- Image coverage: 5 inline images (`image001`–`image005`); modest, do not rely on this baseline for image-path coverage.

Run from `tests/.artifacts/` so generated files stay out of the repo root:

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python ../../scripts/convert.py ../baselines/diligent-dick/diligent-dick.epub --olang zh
# then run translation via the skill
python ../../scripts/merge_and_build.py --temp-dir diligent-dick_temp --title "勤奋的迪克（Alias-Stress Baseline）"
```

## Expected outcome

See `tests/baselines/README.md` for the three-tier convention.

*Forward-looking targets, not yet validated. The first full pipeline run after this section was added is the validation event.*

### Measured

None — no `tests/.artifacts/diligent-dick_temp/` exists yet.

*Conversion-only measurement (2026-10-28, no translation run): this input
converts to **8 chunks** at the current default (`--chunk-size 15000`) and
**16 chunks** at `--chunk-size 6000`. The v1.2.3 chunker dropped the
heading-boundary preference that used to cut this book into ~57 pieces, so a
default run no longer matches the historical count below.*

### Expected target (unverified — needs first full pipeline run)

- `manifest.chunk_count` is 8 at the default size (16 at `--chunk-size 6000`), per the 2026-10-28 conversion-only measurement above; if a later pipeline version changes the split, the first run records the new exact value and this line gets re-recorded. Variance introduced by a chunker change is not a regression, but it must be re-recorded.
- All `chunk*.md` and matching `output_chunk*.md` exist; count matches `manifest.chunk_count`
- 5 inline images preserved (`image001`–`image005`, source-file property — exact)
- All 4 final formats generated: `book.html`, `book.docx`, `book.epub`, `book.pdf`
- **Primary alias assertion**: `Dick` and `Richard` resolve to a *single* glossary entity, both forms present in `aliases`. (Unambiguous nickname relationship.)
- **Critical ambiguity flag** — `Stuart` / `Mr. Stuart` (father vs. son): the disambiguation must surface in `merge_meta prepare-merge` output as **any** decision item (any `kind` — `alias`, `alias_or_new_entity`, `conflicting_new_entity_proposals`, `new_entity_existing_alias`, or `existing_entity_conflict` — whichever fires depends on run state). The non-silent criterion is "main agent gets to judge", regardless of decision kind. It must **NOT** be silently merged into `Dick`; silent merge = loss of evidence = regression.
  - Do **NOT** assert it must appear in the per-chunk meta `conflicts` array; that array is specifically for "injected canonical field vs observed-better value" comparisons (see `scripts/meta.py:21-23`), not general entity ambiguity.
- Once the protagonist has been seen in the first co-occurrence chunks (chunk 1–2 at the default 15000-size run — Dick, Richard and Stuart all appear there; historically chunks 30 and 33 under the old chunker; note at the default concurrency of 24 a single batch already covers all 8 chunks and the batches-vs-chunks numbering no longer differs), the entity must reach `confidence != "low"`. The `merge_meta` "Surface ALL competing proposals" / "Surface ALL alias candidates" fixes (commits `73b5f82`, `bbee9c9`) exist to drive convergence here without waiting for many additional chunks.

### Drift indicator (record current values, do not pass/fail)

- `Dick`/`Richard` final translation: a single Chinese form (not `迪克` and `理查德` mixed in the same output)
- `Mr. Stuart`'s rendering matches whichever resolution wins (consistency only, no specific target value)
