# Test Results — translate-book-parallel-pro

## Test 1: Full Translation — The Time Machine (100 pages)

| Parameter | Value |
|-----------|-------|
| **Book** | The Time Machine by H.G. Wells |
| **Source** | Project Gutenberg (ebook #35) |
| **Target language** | Russian |
| **Chunks** | 17 (chunk_size=15000) |
| **Batches** | 5 batches × 3 sub-agents + 2 manual chunks |
| **Model** | deepseek-v4-flash-free (OpenCode Zen) |
| **Total time** | ~20 minutes (12:44 → 13:04) |
| **Output formats** | EPUB, DOCX, PDF, HTML |
| **Speed** | ~5-7 pages/min (warm) |

### ⚠️ Path Issue (Fixed)

**Root cause:** `convert.py` was run from the Hermes profile directory
(`~/AppData/.../skills/translate-book-parallel-pro/`) instead of the repo root
(`F:/translate-book-parallel-pro/`), causing `time-machine_temp/` to be created
in the profile rather than the repo.

**Fix:** Use `--temp-root <repo>/test-output/` when running from any working directory:

```bash
cd /f/translate-book-parallel-pro
python scripts/convert.py input.epub --olang ru \
  --temp-root test-output/
# → chunks land in: test-output/<book>_temp/
```

### Quality

- All glossary terms preserved (Morlocks→Морлоки, Eloi→Элои, Weena→Уина, etc.)
- Markdown structure intact
- TOC generated (5 headings)
- EPUB validated (no compression errors)
- Adult literature style retained

---

## Test 2: Path Verification (convert from repo root)

| Check | Result |
|-------|--------|
| `convert.py` from `F:/translate-book-parallel-pro/` | ✅ |
| `--temp-root test-output/` respected | ✅ |
| Chunks land in `test-output/time-machine_temp/` | ✅ |
| All 17 chunks generated at 15000 chars | ✅ |
| No files leaked into Hermes profile | ✅ |

---

## Quick Start for New Machine

```bash
# 1. Clone
git clone https://github.com/L-MORIA/translate-book-parallel-pro.git
cd translate-book-parallel-pro

# 2. Install deps
python scripts/setup.py

# 3. Convert + translate (outputs land in test-output/)
python scripts/convert.py book.epub --olang ru --temp-root test-output/

# 4. After sub-agent translation → merge
python scripts/merge_and_build.py \
  --temp-dir test-output/<book>_temp \
  --title "Title" --cleanup
```
