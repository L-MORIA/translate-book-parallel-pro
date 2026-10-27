import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _mab_html  # noqa: E402


LANG_CFG = {"lang_attr": "ru", "font_family": "serif", "toc_label": "Оглавление"}

TEMPLATE = """<!DOCTYPE html>
<html lang="$lang$">
<head>
<title>$title$</title>
</head>
<body>
$body$
</body>
</html>
"""


class SanitizeHtmlBodyTests(unittest.TestCase):
    def test_strips_script_blocks(self):
        body = '<p>ok</p><script>alert(1)</script><p>also ok</p>'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertNotIn("script", cleaned)
        self.assertIn("<p>ok</p>", cleaned)
        self.assertIn("<p>also ok</p>", cleaned)

    def test_strips_script_block_with_attributes_and_newlines(self):
        body = '<p>ok</p><script type="text/javascript">\nvar x = "<b>";\n</script>'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertNotIn("text/javascript", cleaned)
        self.assertNotIn("var x", cleaned)

    def test_strips_open_script_tag_without_close(self):
        body = '<p>ok</p><script src="evil.js">'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertNotIn("<script", cleaned)

    def test_strips_event_handlers(self):
        body = '<img src="x.png" onerror="alert(1)"><p onload=\'x()\'>t</p>'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertNotIn("onerror", cleaned)
        self.assertNotIn("onload", cleaned)
        self.assertIn('<img src="x.png">', cleaned)

    def test_neutralizes_javascript_href(self):
        body = '<a href="javascript:alert(1)">click</a> <a href="https://ok.example">ok</a>'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertNotIn("javascript:", cleaned)
        self.assertIn('href="#"', cleaned)
        self.assertIn('href="https://ok.example"', cleaned)

    def test_neutralizes_javascript_href_with_nested_quotes(self):
        # Regression: the value contains single quotes inside double quotes —
        # the whole quoted value must be replaced, not truncated at the
        # inner quote.
        body = '<a href="javascript:alert(\'pwned\')">x</a>'
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertEqual(cleaned, '<a href="#">x</a>')
        self.assertNotIn("pwned", cleaned)

        body = "<a href='javascript:alert(\"pwned\")'>x</a>"
        cleaned = _mab_html.sanitize_html_body(body)
        self.assertEqual(cleaned, "<a href='#'>x</a>")

    def test_leaves_ordinary_markup_untouched(self):
        body = '<h1 id="ch-1">Глава</h1><p>текст <b>жирный</b> и <img src="a.png" alt="картинка"></p>'
        self.assertEqual(_mab_html.sanitize_html_body(body), body)


class ApplyTemplateEscapingTests(unittest.TestCase):
    def _apply(self, tmp, title, author, body="<p>text</p>"):
        template_file = Path(tmp) / "template.html"
        template_file.write_text(TEMPLATE, encoding="utf-8")
        output_file = Path(tmp) / "out.html"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = _mab_html.apply_template_to_html(
                body, str(template_file), str(output_file), title, LANG_CFG, author=author
            )
        return ok, output_file.read_text(encoding="utf-8")

    def test_escapes_hostile_title(self):
        hostile = '"><script>alert("pwned")</script>'
        with tempfile.TemporaryDirectory() as tmp:
            ok, html = self._apply(tmp, title=hostile, author="Author")
        self.assertTrue(ok)
        self.assertNotIn("<script>", html)
        self.assertIn("&gt;&lt;script&gt;", html)

    def test_escapes_hostile_author_in_meta(self):
        hostile = 'Author"><img src=x onerror=alert(1)>'
        with tempfile.TemporaryDirectory() as tmp:
            ok, html = self._apply(tmp, title="Book", author=hostile)
        self.assertTrue(ok)
        self.assertIn('<meta name="author" content="Author&quot;&gt;&lt;img src=x onerror=alert(1)&gt;">', html)
        self.assertNotIn('<meta name="author" content="Author">', html)

    def test_plain_title_author_pass_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, html = self._apply(tmp, title="Война и мир", author="Л. Н. Толстой")
        self.assertTrue(ok)
        self.assertIn("<title>Война и мир</title>", html)
        self.assertIn('content="Л. Н. Толстой"', html)


class HtmlBuildStampTests(unittest.TestCase):
    """convert_md_to_html produces book_doc.html AND book.html.

    Regression: the skip decision only looked at book_doc.html's mtime, so a
    build whose book.html was missing (or was built with another --title /
    --author / --lang / template) reported success and never regenerated it.
    """

    MD = "# Chapter 1\n\nSome chapter text.\n"
    OTHER_LANG_CFG = {
        "lang_attr": "en",
        "font_family": "Georgia, serif",
        "toc_label": "Contents",
    }

    def _write_md(self, tmp, text=None):
        Path(tmp, "output.md").write_text(text or self.MD, encoding="utf-8")

    def _run(self, tmp, title="Old Title", author="Author", cfg=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = _mab_html.convert_md_to_html(
                str(tmp), title, cfg or LANG_CFG, author
            )
        return ok, buf.getvalue()

    def test_generates_both_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            ok, _ = self._run(tmp)

            self.assertTrue(ok)
            self.assertTrue(Path(tmp, "book_doc.html").is_file())
            self.assertTrue(Path(tmp, "book.html").is_file())

    def test_second_run_skips_unchanged_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp)[0])
            ok, out = self._run(tmp)

            self.assertTrue(ok)
            self.assertIn("Skipping HTML generation", out)

    def test_missing_book_html_is_regenerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp)[0])
            Path(tmp, "book.html").unlink()

            ok, out = self._run(tmp)

            self.assertTrue(ok)
            self.assertIn("missing book.html", out)
            self.assertTrue(Path(tmp, "book.html").is_file())

    def test_title_change_regenerates_book_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp, title="Old Title")[0])

            ok, out = self._run(tmp, title="New Title")
            doc_html = Path(tmp, "book_doc.html").read_text(encoding="utf-8")
            web_html = Path(tmp, "book.html").read_text(encoding="utf-8")

            self.assertTrue(ok)
            self.assertIn("title", out)
            self.assertIn("New Title", doc_html)
            self.assertIn("New Title", web_html)
            self.assertNotIn("Old Title", web_html)

    def test_author_change_regenerates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp, author="First Author")[0])

            ok, out = self._run(tmp, author="Second Author")
            doc_html = Path(tmp, "book_doc.html").read_text(encoding="utf-8")

            self.assertTrue(ok)
            self.assertIn("author", out)
            self.assertIn("Second Author", doc_html)
            self.assertNotIn("First Author", doc_html)

    def test_language_change_regenerates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp)[0])

            ok, out = self._run(tmp, cfg=self.OTHER_LANG_CFG)
            web_html = Path(tmp, "book.html").read_text(encoding="utf-8")

            self.assertTrue(ok)
            self.assertIn("lang_attr", out)
            self.assertIn('lang="en"', web_html)

    def test_output_md_change_regenerates(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write_md(tmp)
            self.assertTrue(self._run(tmp)[0])

            self._write_md(tmp, "# Chapter 2\n\nCompletely different body text.\n")
            ok, out = self._run(tmp)
            web_html = Path(tmp, "book.html").read_text(encoding="utf-8")

            self.assertTrue(ok)
            self.assertIn("output_md_sha256", out)
            self.assertIn("Completely different body text", web_html)


if __name__ == "__main__":
    unittest.main()
