# standard-alice

Full-pipeline baseline input for this repository.

- File: `standard-alice.epub`
- Source: Standard Ebooks edition of *Alice's Adventures in Wonderland*
- Why this baseline: stable EPUB structure, chaptered prose, recurring entities, and many illustrations, which makes it useful for exercising convert, chunking, translation, merge, and final format generation.

## Getting the file (not checked into git)

The 11 MB fixture is not tracked — fetch it on demand from
<https://standardebooks.org/ebooks/lewis-carroll/alices-adventures-in-wonderland>
("Compatible epub" download) and place it at
`tests/baselines/standard-alice/standard-alice.epub`:

```bash
curl -L -o tests/baselines/standard-alice/standard-alice.epub \
  "https://standardebooks.org/ebooks/lewis-carroll/alices-adventures-in-wonderland/downloads/alices_adventures_in_wonderland.epub"
```

Verify the fetched file against the bytes this baseline was measured with:
`sha256sum standard-alice.epub` must print
`d708184c72ccb1848e10e0b456e2ec145c67a3b93ba562fc528cfa07754e5140`
(10 635 439 bytes — the git blob `95f8c238` at `cde660b`, from which the file
was restored when the release stopped tracking it). Standard Ebooks
occasionally re-renders its files — if the hash differs, the Measured values
below must be re-validated before use as pass/fail assertions.

**What `manifest.json`'s `source_hash` is:** the SHA-256 of the *generated
`input.md`*, not of the epub. It depends on the conversion code (cleaning,
chunker version), so it is only comparable between runs of the same pipeline
version — the epub hash above is the right identity check for the file.

Run the repository baseline test from `tests/.artifacts/` so generated files stay out of the repo root:

```bash
mkdir -p tests/.artifacts
cd tests/.artifacts
python ../../scripts/convert.py ../baselines/standard-alice/standard-alice.epub --olang zh
# then run translation via the skill
python ../../scripts/merge_and_build.py --temp-dir standard-alice_temp --title "爱丽丝梦游仙境（Baseline Test）"
```

## Expected outcome

See `tests/baselines/README.md` for the three-tier convention (Measured / Expected target / Drift indicator).

### Measured (historical — pinned to the configuration of that run)

The numbers below come from the v1.2.0-era run and are only reproducible with
its configuration: the 11 MB fixture is **not in git** (verify the SHA-256
below if you re-fetch it) and the run used `target_size=6000`/`concurrency 8`,
both defaults later raised to `--chunk-size 15000` / `24`. Treat them as a
reference from that run; a re-run under current defaults must re-measure and
re-record, not fail against these numbers by default. To reproduce the chunk
level, pass `--chunk-size 6000` to `convert.py`.

Full pipeline run completed at `target_size=6000`, default concurrency 8, 4 batches.

`manifest.json`:
- `chunk_count == 38` (historical; with the v1.2.3+ chunker this input converts to 31 chunks at `--chunk-size 6000` and 13 at the 15000 default — conversion-only measurement of 2026-10-28)
- `source_hash == "6b1ea8ca29311ff8c43740b5a87d3fcfe0b906eb69bdcc74585d81a280f40c09"` (SHA-256 of that run's generated `input.md`; it is not the epub's hash — see the identity note above)
- `chunks[]` has 38 entries, sequential `chunk0001`–`chunk0038`, each with a non-empty `source_hash` and matching `output_file`

Files on disk:
- 38 `chunk0001.md`–`chunk0038.md` source chunks exist
- 38 `output_chunk0001.md`–`output_chunk0038.md` translated chunks exist
- 38 `output_chunk*.meta.json` per-chunk meta files exist
- 45 image files in `images/`

`merge_meta status`:
- `translated_chunks: 38`, `meta_files_found: 38`, `meta_files_consumed: 38`
- `unmerged_meta_files: 0`, `malformed_meta_files: 0`

`glossary.json` (version 2):
- `applied_meta_hashes` has 38 entries (all chunks merged)
- 95 total terms; 22 reach `confidence: "high"` (≥3 `evidence_refs`)
- Major character entities (sample of high-confidence with stable aliases):

| `source` | `target` | `confidence` | `evidence_refs` | `aliases` |
|---|---|---|---|---|
| Alice | 爱丽丝 | high | 5 | [] |
| White Rabbit | 白兔 | high | 5 | ["the Rabbit", "W. Rabbit"] |
| Cheshire Cat | 柴郡猫 | high | 5 | ["Cheshire Puss", "Cat"] |
| Queen of Hearts | 红心皇后 | high | 5 | ["Queen", "the Queen"] |
| King of Hearts | 红心国王 | high | 5 | ["the King"] |
| Bill | 比尔 | high | 5 | ["Lizard"] |
| Caterpillar | 毛毛虫 | high | 5 | [] |
| Hatter | 帽匠 | high | 5 | [] |
| March Hare | 三月兔 | high | 5 | [] |
| Dormouse | 睡鼠 | high | 5 | [] |
| Mock Turtle | 素甲鱼 | high | 5 | [] |
| Gryphon | 鹰头狮 | high | 5 | [] |

Note on the auto-applied `King` (`国王`) entity, separate from `King of Hearts` (`红心国王`): `merge_meta` saw `King` as a new entity in chunks 23/24 with no canonical conflict, so it auto-applied. This creates a (semantically redundant) standalone entity alongside `King of Hearts` (which has `the King` as alias). The pipeline does not currently merge two existing entities; this redundancy is expected output, not a bug. Recorded so a future reader doesn't "fix" it without considering the apply-merge contract.

Note on `Wonderland`, `Frog-Footman`: a few entities carry `confidence: high` without enough `evidence_refs` to satisfy `merge_meta._confidence_for_evidence_count`. This is **not** an anomaly — `scripts/glossary.py` validates `confidence` against the enum only; the merge-time promotion rule applies only inside `_append_evidence_ref`. Seeded or reused entries can legitimately carry high confidence with sparse `evidence_refs`.

Final-format outputs (historical sizes — later releases add a sanitizer, TOC and SVG-unwrap steps, so byte counts differ from a current run):
- `output.md`: 160,705 bytes (merged translated markdown)
- `book.html`: 189,824 bytes (web version with floating TOC)
- `book_doc.html`: 182,797 bytes (ebook-style version)
- `book.docx`: 9,809,493 bytes
- `book.epub`: 9,861,786 bytes (43 of 45 source images preserved end-to-end; 2-image gap is Calibre cover-handling / dedup behavior, not a content regression)
- `book.pdf`: 14,665,137 bytes
- TOC inserted with 18 headings

### Expected target (unverified)

None — all previous targets validated by the run above. If the fixture is re-fetched or the pipeline defaults change, re-measure and re-record here rather than comparing against this historical block.

### Drift indicator (record current values, do not pass/fail)

LLM-dependent, may differ across runs/models. These are *current observed values*, not assertions:
- `Alice.target` = `"爱丽丝"`
- `White Rabbit.target` = `"白兔"`
- `Cheshire Cat.target` = `"柴郡猫"`
- `Queen of Hearts.target` = `"红心皇后"`
- `Mock Turtle.target` = `"素甲鱼"` (chosen over alternative `"假海龟"` via `conflicting_new_entity_proposals` decision; 赵元任 1922 译本经典渲染)
- `Mouse.gender` = `"male"` (Carroll's narrator uses "his")
- `Dinah.gender` = `"female"` (Alice refers to her cat as "she")
- Cross-batch convergence: `Alice`, `White Rabbit`, `Mouse`, `Dinah`, `Lory` reached `confidence: "high"` within the chunks 4–11 prior partial run; remaining 22 high-confidence entities accumulated across batches 1–4 of this completion run. Major-character convergence held at first batch — no late-batch alias drift observed.
