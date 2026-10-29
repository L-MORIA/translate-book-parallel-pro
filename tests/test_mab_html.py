import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _mab_html  # noqa: E402


LANG_CFG = {"lang_attr": "ru", "font_family": "serif", "toc_label": "Оглавление"}
OTHER_LANG_CFG = {
    "lang_attr": "en",
    "font_family": "Georgia, serif",
    "toc_label": "Contents",
}

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
        # Attribute quoting is normalised by the re-serialising sanitizer;
        # what matters is that the whole value was replaced.
        self.assertEqual(cleaned, '<a href="#">x</a>')
        self.assertNotIn("pwned", cleaned)

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


class SanitizeHtmlBodyBypassTests(unittest.TestCase):
    """Payloads that walked straight through the old regex denylist.

    The old sanitizer only understood quoted attribute values and only checked
    href on <a>, so an unquoted onerror, a javascript: iframe or a formaction
    all survived into book.html - which is opened in a browser.
    """

    def _clean(self, body):
        return _mab_html.sanitize_html_body(body)

    def test_unquoted_event_handler(self):
        cleaned = self._clean('<p>ok</p><img src=x onerror=alert(1)>')
        self.assertNotIn("onerror", cleaned.lower())
        self.assertNotIn("alert(1)", cleaned)
        self.assertIn('<img src="x">', cleaned)

    def test_unquoted_event_handler_on_any_element(self):
        cleaned = self._clean('<body onload=alert(1)><p>x</p></body>')
        self.assertNotIn("onload", cleaned.lower())
        self.assertNotIn("alert(1)", cleaned)

    def test_iframe_with_javascript_url_is_removed_with_contents(self):
        cleaned = self._clean('<p>a</p><iframe src="javascript:alert(1)"></iframe><p>b</p>')
        self.assertNotIn("iframe", cleaned.lower())
        self.assertNotIn("javascript:", cleaned.lower())

    def test_formaction_is_treated_as_a_url(self):
        cleaned = self._clean('<button formaction="javascript:alert(1)">go</button>')
        self.assertNotIn("javascript:", cleaned.lower())

    def test_entity_encoded_scheme(self):
        cleaned = self._clean('<a href="java&#115;cript:alert(1)">x</a>')
        self.assertNotIn("script:", cleaned.lower())
        self.assertIn('href="#"', cleaned)

    def test_control_characters_inside_the_scheme(self):
        # Browsers strip tabs/newlines inside a scheme; the sanitizer must see
        # the same URL they do.
        cleaned = self._clean('<a href="jav&#x09;ascript:alert(1)">x</a>')
        self.assertNotIn("ascript:", cleaned.lower())
        self.assertIn('href="#"', cleaned)

    def test_object_and_embed_are_removed(self):
        cleaned = self._clean(
            '<object data="javascript:alert(1)"></object>'
            '<embed src="evil.swf"><p>text</p>'
        )
        self.assertNotIn("object", cleaned.lower())
        self.assertNotIn("embed", cleaned.lower())
        self.assertIn("<p>text</p>", cleaned)

    def test_script_inside_svg_is_removed(self):
        cleaned = self._clean('<svg><script>alert(1)</script></svg>')
        self.assertNotIn("script", cleaned.lower())
        self.assertIn("<svg>", cleaned)

    def test_meta_refresh_is_removed(self):
        cleaned = self._clean('<meta http-equiv="refresh" content="0;url=javascript:alert(1)">')
        self.assertNotIn("http-equiv", cleaned.lower())
        self.assertNotIn("refresh", cleaned.lower())

    def test_style_attribute_with_javascript_url(self):
        cleaned = self._clean('<div style="background:url(javascript:alert(1))">x</div>')
        self.assertNotIn("javascript:", cleaned.lower())
        self.assertIn("<div>x</div>", cleaned)

    def test_data_urls(self):
        picture = '<img src="data:image/png;base64,iVBORw0KGgo=">'
        self.assertEqual(self._clean(picture), picture)

        # Calibre stores bitmap illustrations as base64 SVG wrappers; they are
        # a picture, not a document, so they must survive.
        svg_picture = '<img src="data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=">'
        self.assertEqual(self._clean(svg_picture), svg_picture)

        document = '<a href="data:text/html,<script>alert(1)</script>">x</a>'
        self.assertIn('href="#"', self._clean(document))

        # ...but an SVG is not a navigation target: opening it as a document
        # could run its script.
        navigation = '<a href="data:image/svg+xml,<svg onload=alert(1)>">x</a>'
        self.assertIn('href="#"', self._clean(navigation))

    def test_escaped_markup_in_prose_survives(self):
        # A book about HTML legitimately contains &lt;script&gt; as text; that
        # is not a script and must not be stripped.
        body = "<p>write &lt;script&gt;alert(1)&lt;/script&gt; to test</p>"
        self.assertEqual(self._clean(body), body)

    def test_entities_and_preformatted_text_are_preserved(self):
        body = '<pre><code>a &amp; b &lt; c</code></pre><p title="a &amp; b">x</p>'
        self.assertEqual(self._clean(body), body)

    def test_self_closing_tags_keep_their_slash(self):
        # Inline SVG relies on <path/> semantics: a bare <path> would nest the
        # rest of the illustration inside it.
        cleaned = self._clean(
            '<svg viewBox="0 0 10 10"><path d="M0 0"/><rect width="1"/></svg>'
        )
        self.assertIn('<svg viewbox=', cleaned.lower())
        self.assertIn('viewBox="0 0 10 10"', cleaned)
        self.assertIn('<path d="M0 0" />', cleaned)
        self.assertIn('<rect width="1" />', cleaned)

    def test_svg_names_keep_their_case(self):
        # XHTML/EPUB consumers are case-sensitive: lowercase "viewbox" or
        # "lineargradient" is not a valid SVG element there.
        cleaned = self._clean(
            '<svg viewBox="0 0 4 4"><linearGradient id="g" gradientUnits="userSpaceOnUse">'
            '</linearGradient><clipPath id="c"></clipPath></svg>'
        )
        self.assertIn('viewBox="0 0 4 4"', cleaned)
        self.assertIn('<linearGradient id="g" gradientUnits="userSpaceOnUse">', cleaned)
        self.assertIn('</linearGradient>', cleaned)
        self.assertIn('<clipPath id="c">', cleaned)

    def test_attribute_values_are_escaped_on_re_serialisation(self):
        # The value is re-emitted from the parsed form, so a quote inside an
        # attribute cannot break out of the tag.
        cleaned = self._clean('<p title="a&quot;b">x</p>')
        self.assertEqual(cleaned, '<p title="a&quot;b">x</p>')


class HtmlBuildStampTests(unittest.TestCase):
    """convert_md_to_html produces book_doc.html AND book.html.

    Regression: the skip decision only looked at book_doc.html's mtime, so a
    build whose book.html was missing (or was built with another --title /
    --author / --lang / template) reported success and never regenerated it.
    """

    MD = "# Chapter 1\n\nSome chapter text.\n"

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

            ok, out = self._run(tmp, cfg=OTHER_LANG_CFG)
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


class ConvertWithPandocTests(unittest.TestCase):
    """convert_with_pandoc() — the primary MD→HTML converter. Unit CI has no
    pandoc binary, so the subprocess call is mocked; the command construction
    is what matters."""

    def _stage(self):
        tmp = tempfile.TemporaryDirectory()
        md_file = os.path.join(tmp.name, "output.md")
        html_file = os.path.join(tmp.name, "book.html")
        Path(md_file).write_text("Body text.\n", encoding="utf-8")
        return tmp, md_file, html_file

    def test_builds_the_expected_pandoc_argv(self):
        tmp, md_file, html_file = self._stage()
        with tmp:
            with mock.patch("_mab_html.subprocess.run", return_value=mock.Mock()) as run, \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                ok = _mab_html.convert_with_pandoc(md_file, html_file, "My Title", "ru")

        self.assertTrue(ok)
        self.assertIn("Converted with pandoc", out.getvalue())
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "pandoc")
        self.assertEqual(cmd[1], md_file)
        self.assertEqual(cmd[cmd.index("-o") + 1], html_file)
        self.assertIn("--standalone", cmd)
        self.assertEqual(cmd[cmd.index("--metadata") + 1], "title=My Title")
        self.assertIn("lang=ru", cmd)
        self.assertEqual(cmd[cmd.index("--from") + 1],
                         "markdown+smart+east_asian_line_breaks")
        self.assertEqual(cmd[cmd.index("--to") + 1], "html5")
        self.assertIs(run.call_args.kwargs["check"], True)

    def test_lang_pair_is_a_single_unit_index(self):
        tmp, md_file, html_file = self._stage()
        with tmp:
            with mock.patch("_mab_html.subprocess.run", return_value=mock.Mock()) as run:
                _mab_html.convert_with_pandoc(md_file, html_file, "T", "ja")

        cmd = run.call_args.args[0]
        pairs = {cmd[i + 1] for i, item in enumerate(cmd) if item == "--metadata"}
        self.assertEqual(pairs, {"title=T", "lang=ja"})

    def test_title_may_contain_shell_metacharacters(self):
        title = 'Nursery & «Rhyme» "Special" Edition'
        tmp, md_file, html_file = self._stage()
        with tmp:
            with mock.patch("_mab_html.subprocess.run", return_value=mock.Mock()) as run:
                _mab_html.convert_with_pandoc(md_file, html_file, title, "ru")

        cmd = run.call_args.args[0]
        # argv passing keeps the title verbatim: no shell parsing of & or quotes
        self.assertEqual(cmd[cmd.index("--metadata") + 1], f"title={title}")

    def test_pandoc_failure_returns_false(self):
        tmp, md_file, html_file = self._stage()
        with tmp:
            with mock.patch(
                "_mab_html.subprocess.run",
                side_effect=subprocess.CalledProcessError(1, "pandoc", None, "boom"),
            ), contextlib.redirect_stdout(io.StringIO()) as out:
                ok = _mab_html.convert_with_pandoc(md_file, html_file, "T", "ru")

        self.assertFalse(ok)
        self.assertIn("Pandoc conversion failed: boom", out.getvalue())


if __name__ == "__main__":
    unittest.main()
