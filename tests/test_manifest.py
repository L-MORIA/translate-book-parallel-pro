import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import manifest  # noqa: E402


class ValidateForMergeTests(unittest.TestCase):
    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def _workspace(self, tmp):
        temp_dir = Path(tmp)
        self._write(temp_dir / "input.md", "Source text one.\n\nSource text two.\n")
        self._write(temp_dir / "chunk0001.md", "Source text one.\n")
        self._write(temp_dir / "chunk0002.md", "Source text two.\n")
        self._write(temp_dir / "output_chunk0001.md", "译文一。\n")
        self._write(temp_dir / "output_chunk0002.md", "译文二。\n")
        manifest.create_manifest(
            str(temp_dir),
            ["chunk0001.md", "chunk0002.md"],
            str(temp_dir / "input.md"),
        )
        return temp_dir

    def _validate(self, temp_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok, ordered, warnings = manifest.validate_for_merge(str(temp_dir))
        return ok, ordered, warnings, buf.getvalue()

    def test_passes_with_complete_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            ok, ordered, _, _ = self._validate(temp_dir)

        self.assertTrue(ok)
        self.assertEqual(len(ordered), 2)

    def test_rejects_empty_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            self._write(temp_dir / "output_chunk0002.md", "")
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("Empty output", out)

    def test_rejects_blank_whitespace_only_output(self):
        # Whitespace-only files have bytes on disk but merge to nothing after
        # strip() — a chunk's content would vanish silently without this check.
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            self._write(temp_dir / "output_chunk0002.md", "\n   \n\t\n")
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("Blank output", out)
        self.assertIn("output_chunk0002.md", out)

    def test_rejects_undecodable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            (temp_dir / "output_chunk0002.md").write_bytes(b"\xff\xfe\x00 broken")
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("Unreadable output", out)

    def test_rejects_missing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            (temp_dir / "output_chunk0001.md").unlink()
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIn("Missing output", out)


class ValidateForMergeIntegrityTests(unittest.TestCase):
    """The merge-time integrity gate: stale sources and missing source chunks
    must block the merge, and abnormally short outputs must warn."""

    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def _workspace(self, tmp):
        temp_dir = Path(tmp)
        self._write(temp_dir / "input.md", "Source text one.\n\nSource text two.\n")
        self._write(temp_dir / "chunk0001.md", "Source text one.\n")
        self._write(temp_dir / "chunk0002.md", "Source text two.\n")
        self._write(temp_dir / "output_chunk0001.md", "译文一。\n")
        self._write(temp_dir / "output_chunk0002.md", "译文二。\n")
        manifest.create_manifest(
            str(temp_dir),
            ["chunk0001.md", "chunk0002.md"],
            str(temp_dir / "input.md"),
        )
        return temp_dir

    def _validate(self, temp_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok, ordered, warnings = manifest.validate_for_merge(str(temp_dir))
        return ok, ordered, warnings, buf.getvalue()

    def test_rejects_source_changed_after_splitting(self):
        # A source chunk edited after manifest creation means outputs were
        # translated from different bytes — merging would silently mix them.
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            self._write(temp_dir / "chunk0002.md", "Tampered source text.\n")
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("Source changed since splitting", out)
        self.assertIn("chunk0002.md", out)

    def test_rejects_missing_source_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            (temp_dir / "chunk0001.md").unlink()
            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("Missing source", out)
        self.assertIn("chunk0001.md", out)

    def test_warns_on_suspiciously_short_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = self._workspace(tmp)
            self._write(temp_dir / "output_chunk0001.md", "x")
            ok, ordered, warnings, out = self._validate(temp_dir)

        self.assertTrue(ok)
        self.assertEqual(len(ordered), 2)
        self.assertTrue(any("Suspiciously short" in w for w in warnings))
        self.assertIn("Suspiciously short", out)


class ReadOutputTextTests(unittest.TestCase):
    def test_returns_text_for_utf8_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output_chunk0001.md"
            path.write_text("译文。\n", encoding="utf-8")
            self.assertEqual(manifest.read_output_text(str(path)), "译文。\n")

    def test_returns_none_for_missing_file(self):
        self.assertIsNone(manifest.read_output_text("/nonexistent/path.md"))

    def test_returns_none_for_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output_chunk0001.md"
            path.write_bytes(b"\xff\xfe\x00")
            self.assertIsNone(manifest.read_output_text(str(path)))


class ManifestRobustnessTests(unittest.TestCase):
    """A manifest that exists but cannot be used must block the merge.

    Regression: a truncated manifest.json (crash during the in-place write)
    raised JSONDecodeError out of validate_for_merge, and a manifest without a
    "chunks" key raised KeyError — both inside the integrity gate the rest of
    the pipeline relies on.
    """

    def _write(self, path, content):
        Path(path).write_text(content, encoding="utf-8")

    def _validate(self, temp_dir):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok, ordered, warnings = manifest.validate_for_merge(str(temp_dir))
        return ok, ordered, warnings, buf.getvalue()

    def test_corrupt_manifest_blocks_merge_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            self._write(temp_dir / "chunk0001.md", "Source text.\n")
            self._write(temp_dir / "output_chunk0001.md", "译文。\n")
            self._write(temp_dir / "manifest.json", '{"chunk_count": 1, "chunks": [')

            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("manifest.json is unreadable", out)
        self.assertIn("delete", out)

    def test_manifest_without_chunks_key_blocks_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            self._write(temp_dir / "output_chunk0001.md", "译文。\n")
            self._write(temp_dir / "manifest.json", '{"chunk_count": 0, "source_hash": "abc"}')

            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("no usable 'chunks' array", out)

    def test_malformed_chunk_entry_blocks_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            self._write(temp_dir / "output_chunk0001.md", "译文。\n")
            self._write(
                temp_dir / "manifest.json",
                '{"chunks": [{"id": "chunk0001", "order": 1}]}',
            )

            ok, ordered, _, out = self._validate(temp_dir)

        self.assertFalse(ok)
        self.assertIsNone(ordered)
        self.assertIn("missing source_file, output_file", out)

    def test_load_manifest_raises_manifest_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "manifest.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(manifest.ManifestError):
                manifest.load_manifest(tmp)

    def test_missing_manifest_still_uses_legacy_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "output_chunk0001.md").write_text("译文。\n", encoding="utf-8")
            ok, ordered, warnings, _ = self._validate(Path(tmp))

        self.assertTrue(ok)
        self.assertIsNone(ordered)
        self.assertTrue(any("No manifest.json" in w for w in warnings))

    def test_create_manifest_leaves_no_temp_files_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            self._write(temp_dir / "input.md", "Source text.\n")
            self._write(temp_dir / "chunk0001.md", "Source text.\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                first = manifest.create_manifest(
                    str(temp_dir), ["chunk0001.md"], str(temp_dir / "input.md")
                )
                second = manifest.create_manifest(
                    str(temp_dir), ["chunk0001.md"], str(temp_dir / "input.md")
                )

            leftovers = [p.name for p in temp_dir.iterdir() if p.name.startswith(".manifest-")]

        self.assertEqual(first["chunk_count"], 1)
        self.assertEqual(second["chunk_count"], 1)
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
