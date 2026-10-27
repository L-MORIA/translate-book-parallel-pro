#!/usr/bin/env python
"""Integration smoke gate: the real pipeline (Calibre + pandoc) on the
sleepy-hollow baseline.

Stages: convert.py (real Calibre HTMLZ conversion) -> chunk split ->
manifest -> simulated translation (source chunks copied to output chunks —
the LLM stage stays out of CI) -> merge validation -> HTML conversion ->
TOC insertion.

Run: python tests/integration_smoke.py
Requires ebook-convert (Calibre) and pandoc on PATH.
Set SMOKE_FORMATS=1 to also exercise DOCX/EPUB/PDF generation (slow).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
BASELINE = REPO / "tests" / "baselines" / "sleepy-hollow" / "sleepy-hollow.epub"
ARTIFACTS = REPO / "tests" / ".artifacts"
TEMP_DIR = ARTIFACTS / "sleepy-hollow_temp"


def fail(message):
    print(f"\nSMOKE FAIL: {message}")
    sys.exit(1)


def calibre_available():
    try:
        return subprocess.run(
            ["ebook-convert", "--version"], capture_output=True
        ).returncode == 0
    except FileNotFoundError:
        return False


def main():
    if not BASELINE.is_file():
        fail(f"baseline missing: {BASELINE}")
    if not calibre_available():
        fail("ebook-convert (Calibre) not found on PATH")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(TEMP_DIR, ignore_errors=True)

    print("=== [1/5] convert.py (Calibre HTMLZ -> chunks) ===")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "convert.py"), str(BASELINE),
         "--olang", "zh", "--temp-root", str(ARTIFACTS)],
        cwd=str(REPO),
    )
    if result.returncode != 0:
        fail("convert.py exited non-zero")

    chunks = sorted(TEMP_DIR.glob("chunk*.md"))
    if len(chunks) < 2:
        fail(f"expected the baseline to split into several chunks, got {len(chunks)}")

    # The count depends on how the splitter packs sections, so assert the
    # properties instead of a number: the split must be lossless and must
    # respect --chunk-size (default 15000) as an upper bound.
    input_md = TEMP_DIR / "input.md"
    if not input_md.is_file():
        fail("input.md missing after conversion")
    chunk_bytes = sum(chunk.stat().st_size for chunk in chunks)
    source_bytes = input_md.stat().st_size
    if not 0.98 <= chunk_bytes / source_bytes <= 1.02:
        fail(f"chunks hold {chunk_bytes} bytes of a {source_bytes}-byte input.md")
    oversized = [
        f"{chunk.name} ({len(chunk.read_text(encoding='utf-8'))} chars)"
        for chunk in chunks
        if len(chunk.read_text(encoding="utf-8")) > 15000 * 1.1
    ]
    if oversized:
        fail(f"chunks exceed the 15000-char target: {', '.join(oversized)}")

    manifest_path = TEMP_DIR / "manifest.json"
    if not manifest_path.is_file():
        fail("manifest.json not created")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("chunk_count") != len(chunks):
        fail(f"manifest chunk_count {manifest.get('chunk_count')} != {len(chunks)} chunk files")
    if not (TEMP_DIR / "config.txt").is_file():
        fail("config.txt not created")
    print(f"    {len(chunks)} chunks, manifest + config OK")

    print("=== [2/5] simulate translation (copy chunks to outputs) ===")
    for chunk in chunks:
        shutil.copyfile(chunk, TEMP_DIR / f"output_{chunk.name}")
    # Hostile payload in the "translated" content: the sanitizer must strip
    # active content (script / event handlers / javascript: URLs) from the
    # body of the generated book.html. Template-own scripts (floating TOC JS)
    # are trusted and unaffected. No <img> in the payload — the merge gate's
    # image-divergence check would (correctly) reject that before the
    # sanitizer stage.
    (TEMP_DIR / f"output_{chunks[0].name}").open("a", encoding="utf-8").write(
        '\n<script>alert("pwned-script")</script>'
        '\n<p onload="alert(\'pwned-handler\')">x</p>'
        '\n<a href="javascript:alert(\'pwned-url\')">link</a>\n'
    )

    sys.path.insert(0, str(SCRIPTS))
    import merge_and_build  # noqa: E402

    print("=== [3/5] merge validation + output.md ===")
    if not merge_and_build.merge_markdown_files(str(TEMP_DIR)):
        fail("merge_markdown_files rejected the merge")
    output_md = TEMP_DIR / "output.md"
    if not output_md.is_file() or output_md.stat().st_size == 0:
        fail("output.md missing or empty")

    print("=== [4/5] HTML conversion (pandoc -> template) ===")
    lang_cfg = merge_and_build.get_lang_config("zh")
    if not merge_and_build.convert_md_to_html(str(TEMP_DIR), "睡谷传奇（Smoke Baseline）", lang_cfg):
        fail("convert_md_to_html failed")
    book_html = TEMP_DIR / "book.html"
    if not book_html.is_file():
        fail("book.html not generated")
    html = book_html.read_text(encoding="utf-8")
    if "pwned-script" in html or "pwned-handler" in html or "pwned-url" in html:
        fail("hostile payload survived into book.html — sanitizer regression")
    if "onerror" in html or "javascript:" in html.lower():
        fail("event handler / javascript: URL survived into book.html")

    print("=== [5/5] TOC insertion ===")
    if not merge_and_build.add_toc(str(TEMP_DIR)):
        fail("add_toc failed")
    html = book_html.read_text(encoding="utf-8")
    # The template's container uses a composite class (toc-content simple-toc)
    if 'class="toc-content' not in html:
        fail("TOC container missing after add_toc")
    if 'href="#' not in html:
        fail("TOC anchors missing after add_toc")

    if os.environ.get("SMOKE_FORMATS") == "1":
        print("=== [optional] DOCX/EPUB/PDF via Calibre (SMOKE_FORMATS=1) ===")
        if not merge_and_build.generate_formats(str(TEMP_DIR), lang_cfg["lang_attr"]):
            fail("generate_formats failed")

    print(f"\nSMOKE PASS: {len(chunks)} chunks, output.md {output_md.stat().st_size} bytes, "
          f"book.html {book_html.stat().st_size} bytes")


if __name__ == "__main__":
    main()
