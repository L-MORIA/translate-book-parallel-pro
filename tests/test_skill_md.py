"""Regression tests for SKILL.md - the file is an executable prompt, not docs.

Sub-agents receive sections of SKILL.md verbatim, so a leftover Chinese word in
the Russian prompt or a self-contradictory escaping example lands directly in
the instructions the translator follows.
"""

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parents[1] / "SKILL.md"

RUSSIAN_PROMPT_START = "**If target is Russian (`ru`), use this prompt:**"
RUSSIAN_PROMPT_END = "**Otherwise (default"

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
ALT_EXAMPLE_RE = re.compile(r'`(alt="[^`]*)`')


class _AltCollector(HTMLParser):
    """Collects alt attribute values the way a browser would parse them."""

    def __init__(self):
        super().__init__()
        self.values = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "alt":
                self.values.append(value)


class SkillMdPromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SKILL_MD.read_text(encoding="utf-8")
        cls.lines = cls.text.split("\n")

    def _russian_prompt_lines(self):
        """Lines of the Russian sub-agent prompt, with their 1-based numbers."""
        start = next(
            (i for i, line in enumerate(self.lines) if line.strip() == RUSSIAN_PROMPT_START),
            None,
        )
        self.assertIsNotNone(start, f"Russian prompt marker not found: {RUSSIAN_PROMPT_START}")
        end = next(
            (
                i
                for i, line in enumerate(self.lines[start + 1:], start + 1)
                if line.startswith(RUSSIAN_PROMPT_END)
            ),
            None,
        )
        self.assertIsNotNone(end, f"Russian prompt end marker not found: {RUSSIAN_PROMPT_END}")
        return [(i + 1, self.lines[i]) for i in range(start + 1, end)]

    def _alt_examples(self, marker):
        return [
            snippet
            for line in self.lines
            if marker in line
            for snippet in ALT_EXAMPLE_RE.findall(line)
        ]

    def test_russian_prompt_block_is_present(self):
        numbered = self._russian_prompt_lines()
        body = "\n".join(line for _, line in numbered)
        self.assertGreater(len(numbered), 20, "the Russian prompt looks truncated")
        for expected in ("Переведите markdown-файл", "Контекст соседних фрагментов"):
            self.assertIn(expected, body)

    def test_russian_prompt_has_no_chinese_leakage(self):
        # Only the Russian block is checked: Chinese sub-agent prompts and
        # glossary examples elsewhere in the file are intentional.
        leaked = [(number, line) for number, line in self._russian_prompt_lines() if CJK_RE.search(line)]
        self.assertEqual(
            leaked,
            [],
            "Chinese characters leaked into the Russian sub-agent prompt:\n"
            + "\n".join(f"  SKILL.md:{number}: {line.strip()}" for number, line in leaked),
        )

    def test_russian_prompt_keeps_the_fixed_wording(self):
        body = "\n".join(line for _, line in self._russian_prompt_lines())
        self.assertIn("номера ссылок", body)
        self.assertIn("межфрагментных ссылок", body)

    def test_wrong_and_correct_alt_examples_are_different(self):
        wrong = self._alt_examples("错误示例")
        correct = self._alt_examples("正确示例")
        self.assertTrue(wrong, "no wrong alt example found")
        self.assertTrue(correct, "no correct alt example found")
        overlap = set(wrong) & set(correct)
        self.assertEqual(overlap, set(), f"an example is declared both wrong and correct: {overlap}")

    def test_correct_alt_examples_keep_the_attribute_intact(self):
        correct = self._alt_examples("正确示例")
        self.assertTrue(correct)
        self.assertTrue(
            any("&quot;" in snippet or "“" in snippet for snippet in correct),
            "the correct example should show escaping or typographic quotes",
        )
        for snippet in correct:
            with self.subTest(snippet=snippet):
                # Exactly the two quotes delimiting the value: one more would
                # close alt early, which is what the example warns about.
                self.assertEqual(snippet.count('"'), 2)
                parser = _AltCollector()
                parser.feed(f"<img {snippet} />")
                parser.close()
                self.assertEqual(len(parser.values), 1)
                self.assertIn("喝我", parser.values[0])

    def test_wrong_alt_example_would_really_break(self):
        wrong = self._alt_examples("错误示例")
        self.assertTrue(wrong)
        self.assertGreater(wrong[0].count('"'), 2)


if __name__ == "__main__":
    unittest.main()
