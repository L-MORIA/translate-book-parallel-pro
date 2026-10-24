import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import _mab_toc  # noqa: E402


DOC_WITH_TOC_DIV = (
    "<html><body>"
    '<div class="toc-content"></div>'
    "<h1>{h1}</h1>"
    "<p>text</p>"
    "<h2>{h2}</h2>"
    "<p>more text</p>"
    "</body></html>"
)


def _write_doc(tmp, doc):
    path = Path(tmp) / "book.html"
    path.write_text(doc, encoding="utf-8")
    return path


def _run(func, path):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = func(str(path))
    return ok, path.read_text(encoding="utf-8"), buf.getvalue()


class GenerateHeadingIdTests(unittest.TestCase):
    def test_slugs_plain_text(self):
        self.assertEqual(_mab_toc.generate_heading_id("Chapter One", []), "chapter-one")

    def test_strips_punctuation(self):
        self.assertEqual(_mab_toc.generate_heading_id("What? Is! This...", []), "what-is-this")

    def test_empty_text_falls_back_to_heading(self):
        self.assertEqual(_mab_toc.generate_heading_id("??? !!!", []), "heading")

    def test_deduplicates_with_counter(self):
        first = _mab_toc.generate_heading_id("Chapter", [])
        second = _mab_toc.generate_heading_id("Chapter", [first])
        self.assertEqual(first, "chapter")
        self.assertEqual(second, "chapter-1")

    def test_keeps_unicode_word_chars(self):
        # \w is Unicode-aware — Cyrillic headings must survive as usable ids
        self.assertEqual(
            _mab_toc.generate_heading_id("Глава первая", []),
            "глава-первая",
        )


class GenerateSimpleTocHtmlTests(unittest.TestCase):
    def test_empty_input_returns_empty_string(self):
        self.assertEqual(_mab_toc.generate_simple_toc_html([]), "")

    def test_flat_list_of_entries(self):
        toc = _mab_toc.generate_simple_toc_html([
            {"level": 1, "text": "One", "id": "one"},
            {"level": 1, "text": "Two", "id": "two"},
        ])
        self.assertIn('<a href="#one">One</a>', toc)
        self.assertIn('<a href="#two">Two</a>', toc)
        self.assertEqual(toc.count("<ul>"), 1)
        self.assertEqual(toc.count("</ul>"), 1)

    def test_nests_deeper_levels(self):
        toc = _mab_toc.generate_simple_toc_html([
            {"level": 1, "text": "A", "id": "a"},
            {"level": 2, "text": "B", "id": "b"},
        ])
        self.assertIn("<li><ul>", toc)
        self.assertIn("</ul></li>", toc)

    def test_escapes_heading_text(self):
        # Heading text originates from the untrusted source book — it must
        # render as text, never as markup inside the TOC.
        toc = _mab_toc.generate_simple_toc_html([
            {"level": 1, "text": '<img src=x onerror="alert(1)">', "id": "x"},
        ])
        self.assertIn("&lt;img src=x onerror=&quot;alert(1)&quot;&gt;", toc)
        self.assertNotIn("<img", toc)


class InsertTocWithRegexTests(unittest.TestCase):
    def test_inserts_ids_and_toc_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, DOC_WITH_TOC_DIV.format(h1="Alpha", h2="Beta"))
            ok, html, out = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertTrue(ok)
        self.assertIn('<h1 id="heading-1">Alpha</h1>', html)
        self.assertIn('<h2 id="heading-2">Beta</h2>', html)
        self.assertIn('href="#heading-1">Alpha</a>', html)
        self.assertIn('href="#heading-2">Beta</a>', html)
        self.assertIn("TOC inserted (2 headings)", out)

    def test_attributed_headings_get_ids(self):
        # Regression: pandoc/Calibre emit <hN class="..."> — the old string
        # replace reconstructed the heading without attributes, silently
        # no-oped, and left TOC anchors pointing at ids that never existed.
        doc = (
            '<html><body><div class="toc-content"></div>'
            '<h1 class="calibre1" style="margin:0">Title</h1>'
            "<p>text</p>"
            "</body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, doc)
            ok, html, _ = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertTrue(ok)
        self.assertIn('id="heading-1"', html)
        self.assertIn('class="calibre1"', html)
        self.assertIn('href="#heading-1"', html)

    def test_reuses_existing_pandoc_ids(self):
        # pandoc pre-assigns ids — the TOC must reference them instead of
        # adding a duplicate id attribute to the same tag.
        doc = (
            '<html><body><div class="toc-content"></div>'
            '<h1 id="chapter-1">Chapter 1</h1>'
            "</body></html>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, doc)
            ok, html, _ = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertTrue(ok)
        self.assertEqual(html.count("id="), 1)
        self.assertIn('href="#chapter-1"', html)

    def test_backslash_in_heading_text_does_not_crash_or_inject(self):
        # Regression: heading text used to be concatenated into a re.sub
        # replacement string — '\g' raised re.error (crashing the build) and
        # '\1' spliced match-group content into the document.
        doc = DOC_WITH_TOC_DIV.format(h1="Bad \\g \\1 end", h2="Fine")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, doc)
            ok, html, _ = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertTrue(ok)
        self.assertIn(r"Bad \g \1 end", html)

    def test_escapes_html_in_toc_anchor_text(self):
        doc = DOC_WITH_TOC_DIV.format(h1='<b>Bold</b> & "quotes"', h2="Fine")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, doc)
            ok, html, _ = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertTrue(ok)
        # In the TOC entry the text is tag-stripped and entity-escaped; the
        # heading itself keeps its original inner markup.
        self.assertIn(">Bold &amp; &quot;quotes&quot;</a>", html)
        self.assertIn('<h1 id="heading-1"><b>Bold</b> & "quotes"</h1>', html)

    def test_fails_without_toc_content_div(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, "<html><body><h1>Only heading</h1></body></html>")
            ok, _, out = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertFalse(ok)
        self.assertIn("toc-content div not found", out)

    def test_fails_without_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(
                tmp, '<html><body><div class="toc-content"></div><p>no headings</p></body></html>'
            )
            ok, _, out = _run(_mab_toc.insert_toc_with_regex, path)

        self.assertFalse(ok)
        self.assertIn("No headings found", out)


@unittest.skipUnless(_mab_toc.BS4_AVAILABLE, "beautifulsoup4 not installed")
class InsertTocWithBs4Tests(unittest.TestCase):
    def test_inserts_ids_and_escaped_toc(self):
        doc = DOC_WITH_TOC_DIV.format(h1="Alpha & <i>Beta</i>", h2="Gamma")
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, doc)
            ok, html, out = _run(_mab_toc.insert_toc_with_bs4, path)

        self.assertTrue(ok)
        self.assertIn('id="alpha-beta"', html)
        self.assertIn("toc-content", html)
        # get_text() strips inner markup; the ampersand must still be escaped
        # in the TOC anchor so it renders as text
        self.assertIn(">Alpha &amp; Beta</a>", html)
        self.assertIn("TOC inserted", out)

    def test_fails_without_toc_content_div(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_doc(tmp, "<html><body><h1>Only heading</h1></body></html>")
            ok, _, out = _run(_mab_toc.insert_toc_with_bs4, path)

        self.assertFalse(ok)
        self.assertIn("toc-content div not found", out)


if __name__ == "__main__":
    unittest.main()
