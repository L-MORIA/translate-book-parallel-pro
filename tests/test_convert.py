import contextlib
import inspect
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import convert  # noqa: E402


class ChunkSizeDefaultTests(unittest.TestCase):
    """The library defaults and the CLI default must be the same number."""

    def test_library_defaults_match_the_cli_default(self):
        self.assertEqual(convert.DEFAULT_CHUNK_SIZE, 15000)
        for func in (
            convert.merge_blocks_to_chunks,
            convert.split_markdown_text,
            convert.split_markdown_structured,
        ):
            default = inspect.signature(func).parameters["target_size"].default
            self.assertEqual(default, convert.DEFAULT_CHUNK_SIZE, func.__name__)

    def test_cli_help_advertises_the_same_default(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "convert.py"), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(f"(default: {convert.DEFAULT_CHUNK_SIZE})", result.stdout)


class CleanCalibreMarkersTests(unittest.TestCase):
    def test_removes_known_calibre_artifacts(self):
        content = "\n".join(
            [
                "## Heading {#calibre_link-12 .calibre3}",
                "[**Chapter One**]",
                "Paragraph text{.calibre5} (#calibre_link-2)",
                "::: {.calibre1}",
                "42",
                "broken.ct}",
                "Regular paragraph.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertIn("## Heading", cleaned)
        self.assertIn("**Chapter One**", cleaned)
        self.assertIn("Paragraph text", cleaned)
        self.assertIn("Regular paragraph.", cleaned)
        self.assertNotIn(".calibre", cleaned)
        self.assertNotIn("(#calibre_link-", cleaned)
        self.assertNotIn(":::", cleaned)
        # 42 sits between ::: noise and broken.ct} noise, both calibre artifacts.
        # Context-aware cleaner still drops it — but only because of the neighbors.
        self.assertNotIn("\n42\n", f"\n{cleaned}\n")
        self.assertNotIn("broken.ct}", cleaned)

    def test_preserves_year_in_paragraph(self):
        content = "\n".join(
            [
                "He was born in",
                "1984",
                "and died later.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertIn("1984", cleaned)
        self.assertIn("He was born in", cleaned)
        self.assertIn("and died later.", cleaned)

    def test_preserves_chapter_number_after_heading(self):
        content = "\n".join(
            [
                "## Chapter",
                "",
                "3",
                "",
                "Introduction text follows.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertIn("\n3\n", f"\n{cleaned}\n")
        self.assertIn("## Chapter", cleaned)
        self.assertIn("Introduction text follows.", cleaned)

    def test_drops_digit_line_inside_calibre_fence(self):
        content = "\n".join(
            [
                "Some real paragraph.",
                "::: {.calibre1}",
                "42",
                ":::",
                "More real paragraph.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertNotIn("42", cleaned)
        self.assertNotIn(":::", cleaned)
        self.assertIn("Some real paragraph.", cleaned)
        self.assertIn("More real paragraph.", cleaned)

    def test_drops_digit_line_adjacent_to_ct_marker(self):
        content = "\n".join(
            [
                "Real paragraph above.",
                "7",
                "broken.ct}",
                "Real paragraph below.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertNotIn("\n7\n", f"\n{cleaned}\n")
        self.assertNotIn("broken.ct}", cleaned)

    def test_drops_sequential_page_numbers(self):
        # Six paragraphs separated by sequential page-number footers — clear
        # monotonic spine should be detected and dropped.
        content = "\n".join(
            [
                "Para one.",
                "",
                "1",
                "",
                "Para two.",
                "",
                "2",
                "",
                "Para three.",
                "",
                "3",
                "",
                "Para four.",
                "",
                "4",
                "",
                "Para five.",
                "",
                "5",
                "",
                "Para six.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        for n in ("1", "2", "3", "4", "5"):
            self.assertNotIn(f"\n{n}\n", f"\n{cleaned}\n")
        for p in ("Para one.", "Para two.", "Para three.", "Para four.", "Para five.", "Para six."):
            self.assertIn(p, cleaned)

    def test_preserves_year_among_page_numbers(self):
        # Same page-number spine plus a year (1984) sitting between two page
        # numbers — LNDS picks 1..5 and skips 1984, which stays as content.
        content = "\n".join(
            [
                "Para one.",
                "",
                "1",
                "",
                "Para two.",
                "",
                "2",
                "",
                "He was born in 1984.",
                "Standalone year:",
                "1984",
                "and continued.",
                "",
                "3",
                "",
                "Para three.",
                "",
                "4",
                "",
                "Para four.",
                "",
                "5",
                "",
                "Para five.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        self.assertIn("\n1984\n", f"\n{cleaned}\n")
        for n in ("1", "2", "3", "4", "5"):
            self.assertNotIn(f"\n{n}\n", f"\n{cleaned}\n")

    def test_few_digits_not_treated_as_page_numbers(self):
        # Only three standalone digits — below the LNDS minimum length, so all
        # are preserved (assuming no calibre-noise neighbors).
        content = "\n".join(
            [
                "Intro paragraph.",
                "",
                "1",
                "",
                "Body paragraph.",
                "",
                "2",
                "",
                "More body.",
                "",
                "3",
                "",
                "Closing paragraph.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        for n in ("1", "2", "3"):
            self.assertIn(f"\n{n}\n", f"\n{cleaned}\n")

    def test_non_monotonic_digits_preserved(self):
        # Five standalone digits but no monotonic spine — LNDS coverage too low
        # to trigger; everything preserved.
        content = "\n".join(
            [
                "Intro.",
                "",
                "1984",
                "",
                "Para A.",
                "",
                "42",
                "",
                "Para B.",
                "",
                "7",
                "",
                "Para C.",
                "",
                "1066",
                "",
                "Para D.",
                "",
                "3",
                "",
                "Closing.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content)

        for n in ("1984", "42", "7", "1066", "3"):
            self.assertIn(f"\n{n}\n", f"\n{cleaned}\n")

    def test_strip_page_numbers_flag_restores_legacy(self):
        content = "\n".join(
            [
                "He was born in",
                "1984",
                "and died later.",
                "",
                "## Chapter",
                "",
                "3",
                "",
                "Introduction text follows.",
            ]
        )

        cleaned = convert.clean_calibre_markers(content, strip_page_numbers=True)

        self.assertNotIn("1984", cleaned)
        self.assertNotIn("\n3\n", f"\n{cleaned}\n")
        self.assertIn("He was born in", cleaned)
        self.assertIn("Introduction text follows.", cleaned)


class TempRootTests(unittest.TestCase):
    def test_build_temp_dir_preserves_cwd_local_default(self):
        self.assertEqual(convert.build_temp_dir("/books/Alice.epub"), "Alice_temp")

    def test_build_temp_dir_uses_explicit_root(self):
        self.assertEqual(
            convert.build_temp_dir("/books/Alice.epub", "/tmp/work"),
            os.path.join("/tmp/work", "Alice_temp"),
        )

    def test_setup_temp_directory_uses_explicit_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "work"
            html_file = Path(temp_dir) / "input.html"
            images_dir = Path(temp_dir) / "images"
            image_file = images_dir / "cover.jpg"
            html_file.write_text("<html></html>", encoding="utf-8")
            images_dir.mkdir()
            image_file.write_text("image", encoding="utf-8")

            created = convert.setup_temp_directory(
                "/books/Alice.epub",
                str(html_file),
                str(images_dir),
                temp_root=str(root),
            )

            self.assertEqual(created, str(root / "Alice_temp"))
            self.assertTrue((root / "Alice_temp" / "input.html").exists())
            self.assertTrue((root / "Alice_temp" / "images" / "cover.jpg").exists())


class StripPageNumbersCacheConflictTests(unittest.TestCase):
    def test_no_blockers_when_flag_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_md = os.path.join(tmp, "input.md")
            with open(input_md, "w", encoding="utf-8") as f:
                f.write("placeholder")
            with open(os.path.join(tmp, "chunk0001.md"), "w", encoding="utf-8") as f:
                f.write("placeholder")

            blockers = convert._check_strip_page_numbers_cache_conflict(
                strip_flag=False, temp_dir=tmp, input_md=input_md
            )

            self.assertEqual(blockers, [])

    def test_no_blockers_when_temp_dir_missing(self):
        missing_dir = os.path.join(tempfile.gettempdir(), "definitely-not-here-xyz-123")
        # Make extra sure it really doesn't exist.
        self.assertFalse(os.path.isdir(missing_dir))
        input_md = os.path.join(missing_dir, "input.md")

        blockers = convert._check_strip_page_numbers_cache_conflict(
            strip_flag=True, temp_dir=missing_dir, input_md=input_md
        )

        self.assertEqual(blockers, [])

    def test_aborts_when_input_md_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_md = os.path.join(tmp, "input.md")
            with open(input_md, "w", encoding="utf-8") as f:
                f.write("cached markdown")

            blockers = convert._check_strip_page_numbers_cache_conflict(
                strip_flag=True, temp_dir=tmp, input_md=input_md
            )

            self.assertEqual(len(blockers), 1)
            self.assertIn("input.md", blockers[0])

    def test_aborts_when_chunks_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_md = os.path.join(tmp, "input.md")  # absent
            for i in range(1, 4):
                with open(os.path.join(tmp, f"chunk{i:04d}.md"), "w", encoding="utf-8") as f:
                    f.write("chunk")
            # output_chunk*.md files must not be counted as source chunks.
            with open(os.path.join(tmp, "output_chunk0001.md"), "w", encoding="utf-8") as f:
                f.write("translated")

            blockers = convert._check_strip_page_numbers_cache_conflict(
                strip_flag=True, temp_dir=tmp, input_md=input_md
            )

            self.assertEqual(len(blockers), 1)
            self.assertIn("3 chunk file(s)", blockers[0])


class SourceFingerprintCacheTests(unittest.TestCase):
    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def test_no_conflict_for_fresh_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            self._write(source, "source bytes")

            status, message = convert.check_source_cache(
                str(Path(tmp) / "book_temp"),
                convert.source_fingerprint(str(source)),
            )

        self.assertIsNone(status)
        self.assertIsNone(message)

    def test_adopts_cache_that_predates_fingerprinting(self):
        # Temp dirs created before this feature have no fingerprint file.
        # They must stay resumable (trust-on-first-use), with a warning.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            temp_dir = Path(tmp) / "book_temp"
            temp_dir.mkdir()
            self._write(source, "source bytes")
            self._write(temp_dir / "input.html", "<html></html>")

            status, message = convert.check_source_cache(
                str(temp_dir), convert.source_fingerprint(str(source))
            )

        self.assertEqual(status, "adopt")
        self.assertIn(convert.SOURCE_FINGERPRINT_FILE, message)

    def test_mismatch_when_source_bytes_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            temp_dir = Path(tmp) / "book_temp"
            temp_dir.mkdir()
            self._write(source, "old source bytes")
            convert._write_source_fingerprint(
                str(temp_dir), convert.source_fingerprint(str(source))
            )
            self._write(temp_dir / "input.html", "<html></html>")

            self._write(source, "new source bytes!!")
            status, message = convert.check_source_cache(
                str(temp_dir), convert.source_fingerprint(str(source))
            )

        self.assertEqual(status, "mismatch")
        self.assertIn("different source bytes", message)

    def test_no_conflict_when_source_bytes_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            temp_dir = Path(tmp) / "book_temp"
            temp_dir.mkdir()
            self._write(source, "source bytes")
            convert._write_source_fingerprint(
                str(temp_dir), convert.source_fingerprint(str(source))
            )
            self._write(temp_dir / "input.html", "<html></html>")

            status, message = convert.check_source_cache(
                str(temp_dir), convert.source_fingerprint(str(source))
            )

        self.assertIsNone(status)
        self.assertIsNone(message)

    def test_moving_source_file_does_not_invalidate_cache(self):
        # Only content identity matters — renaming/moving the book is fine.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            temp_dir = Path(tmp) / "book_temp"
            temp_dir.mkdir()
            self._write(source, "source bytes")
            convert._write_source_fingerprint(
                str(temp_dir), convert.source_fingerprint(str(source))
            )
            self._write(temp_dir / "input.html", "<html></html>")

            moved = Path(tmp) / "renamed-book.epub"
            source.rename(moved)
            status, _ = convert.check_source_cache(
                str(temp_dir), convert.source_fingerprint(str(moved))
            )

        self.assertIsNone(status)

    def test_corrupt_fingerprint_file_is_adopted_not_crashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "book.epub"
            temp_dir = Path(tmp) / "book_temp"
            temp_dir.mkdir()
            self._write(source, "source bytes")
            self._write(temp_dir / "input.html", "<html></html>")
            self._write(temp_dir / convert.SOURCE_FINGERPRINT_FILE, "{not json")

            status, _ = convert.check_source_cache(
                str(temp_dir), convert.source_fingerprint(str(source))
            )

        self.assertEqual(status, "adopt")


class LinkPreservingMarkerTests(unittest.TestCase):
    def test_bold_brackets_still_cleaned(self):
        cleaned = convert.clean_calibre_markers("[**Chapter One**]")
        self.assertEqual(cleaned, "**Chapter One**")

    def test_real_markdown_links_with_bold_anchors_survive(self):
        # Regression: the cleaner used to turn [**Chapter 1**](chapter1.xhtml)
        # into **Chapter 1**(chapter1.xhtml), silently corrupting TOC links
        # that Calibre/pandoc emit for almost every book.
        content = "[**Chapter 1**](chapter1.xhtml)\n\n[**Chapter 2**][ref]\n"
        cleaned = convert.clean_calibre_markers(content)

        self.assertIn("[**Chapter 1**](chapter1.xhtml)", cleaned)
        self.assertIn("[**Chapter 2**][ref]", cleaned)


class ParseStructuralBlocksTests(unittest.TestCase):
    def test_classifies_common_block_types(self):
        content = "\n".join([
            "# Title",
            "",
            "Para one",
            "continues here.",
            "",
            "```python",
            "code = 1",
            "```",
            "",
            "> quoted line",
            "> more quote",
            "",
            "| a | b |",
            "|---|---|",
            "",
            "- item one",
            "- item two",
            "",
            "![img](pic.png)",
            "",
            "Final para.",
        ])

        blocks = convert.parse_structural_blocks(content)
        types = [btype for _, btype in blocks]

        for expected in ("heading", "code_block", "blockquote", "table", "list", "image", "paragraph"):
            self.assertIn(expected, types)

    def test_paragraph_lines_stay_together(self):
        blocks = convert.parse_structural_blocks("Line one\nLine two\n")
        paragraphs = [text for text, btype in blocks if btype == "paragraph" and text.strip()]
        self.assertEqual(paragraphs, ["Line one\nLine two"])

    def test_fenced_code_block_never_split_by_other_rules(self):
        content = "```text\n# not a heading\n> not a quote\n- not a list\n```\n"
        blocks = convert.parse_structural_blocks(content)
        # Trailing newline may yield a final empty paragraph block; the code
        # block itself must be captured whole and classified as code.
        self.assertEqual(
            blocks[0],
            ("```text\n# not a heading\n> not a quote\n- not a list\n```", "code_block"),
        )
        self.assertTrue(all(btype != "heading" and btype != "list" for _, btype in blocks))


class MergeBlocksToChunksTests(unittest.TestCase):
    def test_splits_at_heading_boundaries(self):
        # 100-word paragraph (~500 chars) fits inside target_size together
        # with its heading, so each chapter packs into one chunk
        chapter = "# Chapter\n\n" + ("word " * 100).strip() + "\n\n"
        content = chapter * 2
        blocks = convert.parse_structural_blocks(content)
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=600)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("# Chapter"))
        self.assertTrue(chunks[1].startswith("# Chapter"))

    def test_small_content_stays_single_chunk(self):
        blocks = convert.parse_structural_blocks("# H\n\ntext\n")
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=6000)
        self.assertEqual(len(chunks), 1)

    def test_short_sections_pack_into_one_chunk(self):
        # Regression (C-03): every heading used to force a flush, so 10 short
        # sections at --chunk-size 15000 became 10 chunks of ~513 chars - ten
        # times the sub-agents, cost and time the caller asked for, each one
        # too small to translate coherently.
        content = "\n\n".join(
            f"### Section {i}\n\n" + ("word " * 100).strip() for i in range(1, 11)
        )
        blocks = convert.parse_structural_blocks(content)
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=15000)

        self.assertEqual(len(chunks), 1)
        self.assertIn("### Section 10", chunks[0])

    def test_heading_still_breaks_a_half_full_chunk(self):
        section = "# {name}\n\n" + ("word " * 150).strip()
        blocks = convert.parse_structural_blocks(
            section.format(name="One") + "\n\n" + section.format(name="Two")
        )
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=1200)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].startswith("# One"))
        self.assertTrue(chunks[1].startswith("# Two"))

    def test_packing_keeps_chunk_size_an_upper_bound(self):
        # Merging short sections must not let a chunk grow past target_size.
        content = "\n\n".join(
            f"### Section {i}\n\n" + ("word " * 40).strip() for i in range(1, 41)
        )
        blocks = convert.parse_structural_blocks(content)
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=1000)

        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            # Block sizes are measured without the newlines that join them,
            # hence the small allowance.
            self.assertLessEqual(len(chunk), 1100)

    def test_no_content_loss_on_merge(self):
        content = "\n\n".join(
            f"# Chapter {i}\n\n" + ("word " * 30).strip() for i in range(1, 11)
        )
        blocks = convert.parse_structural_blocks(content)
        chunks = convert.merge_blocks_to_chunks(blocks, target_size=200)

        self.assertGreater(len(chunks), 1)
        rejoined_word_count = sum(chunk.split().count("word") for chunk in chunks)
        self.assertEqual(rejoined_word_count, content.count("word"))
        rejoined_heading_count = sum(chunk.count("# Chapter") for chunk in chunks)
        self.assertEqual(rejoined_heading_count, 10)


class ForceSplitBlockTests(unittest.TestCase):
    def test_splits_oversized_paragraph_by_blank_lines(self):
        text = "\n\n".join(" ".join(["word"] * 50) for _ in range(6))
        parts = convert._force_split_block(text, target_size=200)

        self.assertGreater(len(parts), 1)
        rejoined = "\n\n".join(parts)
        self.assertEqual(rejoined.count("word"), text.count("word"))

    def test_long_single_lines_split_by_lines(self):
        # No blank lines, so paragraph-splitting is skipped and the block is
        # split at line granularity
        text = "\n".join(" ".join(["word"] * 50) for _ in range(4))
        parts = convert._force_split_block(text, target_size=200)

        self.assertGreater(len(parts), 1)
        self.assertEqual("\n".join(parts), text)

    def test_single_unbroken_line_returned_as_is(self):
        # A single line with no separators cannot be split at line granularity
        # — the block is returned whole (documented limitation).
        text = " ".join(["word"] * 100)
        parts = convert._force_split_block(text, target_size=200)

        self.assertEqual(parts, [text])

    def test_code_blocks_keep_valid_fences_per_chunk(self):
        body_lines = "\n".join(f"print({i})" for i in range(100))
        code = f"```python\n{body_lines}\n```"
        parts = convert._force_split_block(code, target_size=200)

        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertTrue(part.startswith("```python"))
            self.assertTrue(part.endswith("```"))
        rejoined_body = "\n".join(
            "\n".join(part.split("\n")[1:-1]) for part in parts
        )
        self.assertEqual(rejoined_body, body_lines)


class SplitMarkdownStructuredTests(unittest.TestCase):
    def test_end_to_end_split_preserves_all_content(self):
        content = "\n\n".join(
            f"# Chapter {i}\n\n" + ("sentence " * 80).strip() for i in range(1, 6)
        )
        with tempfile.TemporaryDirectory() as tmp:
            md_file = Path(tmp) / "input.md"
            md_file.write_text(content, encoding="utf-8")

            chunk_files = convert.split_markdown_structured(
                str(md_file), tmp, target_size=600
            )

            self.assertGreaterEqual(len(chunk_files), 2)
            self.assertEqual(chunk_files[0], "chunk0001.md")
            rejoined = "\n".join(
                (Path(tmp) / name).read_text(encoding="utf-8") for name in chunk_files
            )
            self.assertEqual(rejoined.count("sentence"), content.count("sentence"))
            self.assertEqual(rejoined.count("# Chapter"), 5)

    def test_empty_file_produces_single_empty_chunk(self):
        # Documented edge behavior: empty input yields one empty chunk file
        # (later merge validation rejects blank translations for it).
        with tempfile.TemporaryDirectory() as tmp:
            md_file = Path(tmp) / "input.md"
            md_file.write_text("", encoding="utf-8")

            chunk_files = convert.split_markdown_structured(str(md_file), tmp)

            self.assertEqual(chunk_files, ["chunk0001.md"])
            self.assertEqual((Path(tmp) / "chunk0001.md").read_text(encoding="utf-8"), "")


class ChunkSetReuseTests(unittest.TestCase):
    """Re-running convert.py must never "validate" an incomplete chunk set.

    The regression these tests pin down: delete 2 of 3 chunk files plus the
    manifest, re-run convert, and the old code rebuilt the manifest from the
    single surviving chunk and reported success — the book silently shipped
    with two thirds of its text missing.
    """

    def _source(self):
        # ~4000 chars per section: with the heading break at half of
        # --chunk-size 6000, each section is its own chunk.
        return "\n\n".join(
            f"# Section {i}\n\n" + ("word " * 800).strip() for i in range(1, 4)
        )

    def _split(self, tmp, chunk_size=6000):
        md_file = Path(tmp) / "input.md"
        md_file.write_text(self._source(), encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            count = convert._do_split_and_manifest(tmp, str(md_file), chunk_size)
        return md_file, count, buf.getvalue()

    def _rerun(self, tmp, md_file, chunk_size=6000):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            count = convert._do_split_and_manifest(tmp, str(md_file), chunk_size)
        return count, buf.getvalue()

    def test_complete_chunk_set_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 3)
            self.assertIn("validated against input.md", out)
            self.assertEqual(len(convert._find_existing_chunk_files(tmp)), 3)

    def test_refuses_when_chunk_files_were_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            for name in ("chunk0002.md", "chunk0003.md"):
                os.remove(os.path.join(tmp, name))
            os.remove(os.path.join(tmp, "manifest.json"))

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 0)
            self.assertIn("refusing to reuse", out)
            self.assertIn("the split looks incomplete", out)
            self.assertIn("produces 3", out)
            # The manifest must not be rewritten from the partial set.
            self.assertFalse(os.path.exists(os.path.join(tmp, "manifest.json")))

    def test_refuses_gap_in_chunk_numbering(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            os.remove(os.path.join(tmp, "chunk0001.md"))

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 0)
            self.assertIn("chunk numbering has gaps", out)
            self.assertIn("chunk0001.md", out)

    def test_refuses_truncated_chunk(self):
        # A single truncated chunk stays inside any sane total-size tolerance on
        # a long book, so the content comparison has to catch it.
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            last = os.path.join(tmp, "chunk0003.md")
            text = Path(last).read_text(encoding="utf-8")
            Path(last).write_text(text[: len(text) // 2], encoding="utf-8")

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 0)
            self.assertIn("chunk0003.md", out)
            self.assertIn("differs from a fresh split", out)

    def test_refuses_chunk_set_built_with_another_chunk_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp, chunk_size=1500)
            self.assertGreater(first, 3)

            count, out = self._rerun(tmp, md_file, chunk_size=6000)

            self.assertEqual(count, 0)
            self.assertIn("--chunk-size 6000", out)
            self.assertIn("nothing is lost", out)

    def test_damaged_own_split_is_safe_to_regenerate(self):
        # Same splitter, missing files: regenerating keeps chunk numbers, so
        # the advice is plain "delete chunk*.md and re-run".
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            Path(tmp, "output_chunk0001.md").write_text("译文一。\n", encoding="utf-8")
            os.remove(os.path.join(tmp, "chunk0002.md"))

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 0)
            self.assertIn("chunk numbering has gaps", out)
            self.assertIn("translations stay valid", out)

    def test_foreign_split_with_translations_warns_about_misalignment(self):
        # The dangerous case: a finished translation of a set built at another
        # --chunk-size. Re-splitting renumbers the source under every output,
        # so the advice must not be "delete chunk*.md and keep translating".
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp, chunk_size=1500)
            self.assertGreater(first, 3)
            for name in ("output_chunk0001.md", "output_chunk0002.md"):
                Path(tmp, name).write_text("译文。\n", encoding="utf-8")

            count, out = self._rerun(tmp, md_file, chunk_size=6000)

            self.assertEqual(count, 0)
            self.assertIn("attached to the wrong source text", out)
            self.assertIn("start a fresh temp directory", out)
            self.assertNotIn("stay valid", out)

    def test_missing_input_md_reuses_contiguous_chunks_with_warning(self):
        # Nothing to compare against, but a contiguous set is still usable.
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            os.remove(md_file)

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 3)
            self.assertIn("without a content check", out)

    def test_refuses_foreign_chunk_named_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            md_file, first, _ = self._split(tmp)
            self.assertEqual(first, 3)
            Path(tmp, "chunknotes.md").write_text("not a chunk", encoding="utf-8")

            count, out = self._rerun(tmp, md_file)

            self.assertEqual(count, 0)
            self.assertIn("chunknotes.md is not a chunkNNNN.md file", out)


if __name__ == "__main__":
    unittest.main()
