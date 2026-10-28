import base64
import inspect
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import calibre_html_publish  # noqa: E402


class ConvertHtmlWithCalibreTests(unittest.TestCase):
    def test_builds_expected_epub_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout, **kwargs):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html), str(output_file), "epub", timeout=12, lang="ja"
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertEqual(cmd[0], "/usr/bin/ebook-convert")
            self.assertEqual(cmd[1], str(input_html))
            self.assertEqual(cmd[2], str(output_file))
            self.assertIn("--title", cmd)
            self.assertIn("--authors", cmd)
            self.assertIn("--language", cmd)
            self.assertIn("ja", cmd)
            self.assertIn("--epub-version", cmd)
            self.assertIn("3", cmd)
            self.assertNotIn("--disable-font-rescaling", cmd)

    @unittest.skipUnless(
        "cover" in inspect.signature(calibre_html_publish.convert_html_with_calibre).parameters,
        "cover parameter unavailable",
    )
    def test_includes_cover_argument_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.epub"
            cover_file = Path(temp_dir) / "cover.jpg"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")
            cover_file.write_text("img", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout, **kwargs):
                output_file.write_text("epub", encoding="utf-8")
                return mock.Mock(returncode=0, stderr="")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ) as run_mock:
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html),
                    str(output_file),
                    "epub",
                    timeout=12,
                    lang="ja",
                    cover=str(cover_file),
                )

            self.assertTrue(ok)
            cmd = run_mock.call_args.args[0]
            self.assertIn("--cover", cmd)
            self.assertIn(str(cover_file), cmd)

    def test_removes_partial_output_after_failed_conversion(self):
        # Calibre writes the output as it goes; a truncated .docx left behind
        # would be treated as "up to date" by the next build.
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.docx"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")

            def fake_run(cmd, capture_output, text, timeout, **kwargs):
                output_file.write_bytes(b"partial")
                return mock.Mock(returncode=1, stderr="ERROR: Conversion to DOCX failed!")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess, "run", side_effect=fake_run
            ):
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html), str(output_file), "docx", timeout=12, lang="ru"
                )

            self.assertFalse(ok)
            self.assertFalse(output_file.exists())

    def test_keeps_previous_output_when_conversion_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "input.html"
            output_file = Path(temp_dir) / "output.docx"
            input_html.write_text("<html><head><title>Book</title></head></html>", encoding="utf-8")
            output_file.write_bytes(b"previous good output")

            with mock.patch.object(
                calibre_html_publish, "find_calibre_convert", return_value="/usr/bin/ebook-convert"
            ), mock.patch.object(
                calibre_html_publish, "extract_html_metadata", return_value=("Book", "Author")
            ), mock.patch.object(
                calibre_html_publish.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stderr="boom"),
            ):
                ok = calibre_html_publish.convert_html_with_calibre(
                    str(input_html), str(output_file), "docx", timeout=12, lang="ru"
                )

            self.assertFalse(ok)
            self.assertEqual(output_file.read_bytes(), b"previous good output")


class UnwrapSvgDataUriImagesTests(unittest.TestCase):
    """Calibre wraps bitmaps in an SVG data URI that its DOCX writer cannot read."""

    @staticmethod
    def _wrapper(inner_svg, extra_attrs=' class="calibre"'):
        payload = base64.b64encode(inner_svg.encode("utf-8")).decode("ascii")
        return f'<img src="data:image/svg+xml;base64,{payload}"{extra_attrs}>'

    def test_points_img_at_the_wrapped_bitmap(self):
        tag = self._wrapper(
            '<svg viewBox="0 0 10 10"><image width="10" height="10" '
            'href="images/000000.jpg"></image></svg>'
        )
        cleaned = calibre_html_publish._unwrap_svg_data_uri_images(f'<p>{tag}</p>')
        self.assertIn('src="images/000000.jpg"', cleaned)
        self.assertIn('class="calibre"', cleaned)
        self.assertNotIn('data:image/svg', cleaned)

    def test_supports_xlink_href_and_single_quotes(self):
        tag = self._wrapper(
            "<svg><image xlink:href='images/pic 1.png'/></svg>"
        ).replace('src="', "src='").replace('" class=', "' class=")
        cleaned = calibre_html_publish._unwrap_svg_data_uri_images(tag)
        self.assertIn("images/pic 1.png", cleaned)
        self.assertNotIn('data:image/svg', cleaned)

    def test_leaves_plain_raster_data_uri_alone(self):
        tag = '<img src="data:image/png;base64,iVBORw0KGgo=" alt="x">'
        self.assertEqual(calibre_html_publish._unwrap_svg_data_uri_images(tag), tag)

    def test_leaves_vector_svg_without_bitmap_alone(self):
        tag = self._wrapper('<svg><path d="M0 0"/></svg>')
        self.assertEqual(calibre_html_publish._unwrap_svg_data_uri_images(tag), tag)

    def test_leaves_malformed_base64_alone(self):
        tag = '<img src="data:image/svg+xml;base64,!!!not-base64!!!">'
        self.assertEqual(calibre_html_publish._unwrap_svg_data_uri_images(tag), tag)

    def test_prepare_html_for_conversion_rewrites_work_copy(self):
        tag = self._wrapper('<svg><image href="images/000000.jpg"/></svg>')
        with tempfile.TemporaryDirectory() as temp_dir:
            input_html = Path(temp_dir) / "book_doc.html"
            input_html.write_text(
                f"<html><head><title>B</title></head><body>{tag}</body></html>",
                encoding="utf-8",
            )
            work_html = calibre_html_publish.prepare_html_for_conversion(
                str(input_html), temp_dir, "ru"
            )
            content = Path(work_html).read_text(encoding="utf-8")
        self.assertIn('src="images/000000.jpg"', content)
        self.assertNotIn('data:image/svg', content)


if __name__ == "__main__":
    unittest.main()
