"""Static checks for the user-facing launcher scripts.

The launcher and the shortcut script are interactive Windows-only files, so CI
cannot run them - but the defects found in the audit were plain mismatches with
the Python pipeline (a format the converter rejects, a title override, a
PowerShell 6 escape). Those a text check catches.
"""

import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
BAT = REPO / "scripts" / "translate-launcher.bat"
PS1 = REPO / "scripts" / "create-desktop-shortcut.ps1"


class LauncherBatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = BAT.read_text(encoding="utf-8")

    def test_does_not_advertise_txt_support(self):
        # convert.py answers "Unsupported file type: .txt" and exits 1.
        self.assertNotIn("epub, pdf, docx, txt", self.text.lower())
        self.assertNotIn("*.txt", self.text)

    def test_accepts_exactly_the_supported_extensions(self):
        for ext in ("epub", "pdf", "docx"):
            self.assertIn(f'"%EXT%"=="{ext}"', self.text)
        self.assertNotIn('"%EXT%"=="txt"', self.text)

    def test_installs_dependencies_into_the_same_interpreter(self):
        # A bare "pip install" can target another Python than the "python"
        # used for the pipeline.
        self.assertNotIn("\npip install", self.text)
        self.assertIn("python -m pip install", self.text)

    def test_does_not_override_the_metadata_title(self):
        # merge_and_build.py prefers original_title from config.txt (book
        # metadata) and falls back to the input file name; passing
        # --title "%BOOK_NAME%" here used to overwrite the real title.
        command_lines = [
            line for line in self.text.splitlines() if not line.lstrip().startswith("::")
        ]
        self.assertNotIn("--title", "\n".join(command_lines))

    def test_moves_each_format_independently(self):
        # A failed EPUB used to hide a good DOCX/PDF: results were moved only
        # inside "if exist book.epub".
        self.assertNotIn('if exist "%TEMP_DIR%\\book.epub"', self.text)
        for name in ("book.epub", "book.docx", "book.pdf", "book.html"):
            self.assertIn(f'move "%TEMP_DIR%\\{name}"', self.text)

    def test_build_failure_message_mentions_formats(self):
        self.assertIn("format conversion failed", self.text)

    def test_banner_has_no_hardcoded_version(self):
        self.assertNotIn("v1.0", self.text)


class DesktopShortcutTests(unittest.TestCase):
    def test_uses_a_powershell_5_compatible_escape(self):
        # `u{...} is PowerShell 6+; .ps1 files are usually run by 5.1, which
        # prints the escape literally.
        text = PS1.read_text(encoding="utf-8")
        self.assertNotIn("`u{", text)
        self.assertIn("ConvertFromUtf32(0x2705)", text)

    def test_description_matches_supported_formats(self):
        text = PS1.read_text(encoding="utf-8")
        self.assertNotIn("TXT", text)


if __name__ == "__main__":
    unittest.main()
