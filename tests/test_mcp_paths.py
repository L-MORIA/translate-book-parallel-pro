import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from translate_book_mcp.paths import PathError, Workspace  # noqa: E402


class WorkspaceConfinementTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.ws = Workspace(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_resolve_dir_accepts_relative_and_absolute_inside_root(self):
        inside = self.root / 'book_temp'
        inside.mkdir()
        self.assertEqual(self.ws.resolve_dir('book_temp'), inside)
        self.assertEqual(self.ws.resolve_dir(str(inside)), inside)

    def test_resolve_dir_rejects_dotdot_escape(self):
        with self.assertRaises(PathError):
            self.ws.resolve_dir('../outside')
        with self.assertRaises(PathError):
            self.ws.resolve_dir('book_temp/../../outside')

    def test_resolve_dir_rejects_absolute_outside_root(self):
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(PathError):
                self.ws.resolve_dir(str(Path(other).resolve()))

    def test_resolve_dir_rejects_symlink_escape(self):
        outside = Path(tempfile.mkdtemp()).resolve()
        link = self.root / 'escape'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation not permitted on this platform')
        try:
            with self.assertRaises(PathError):
                self.ws.resolve_dir('escape')
        finally:
            link.unlink()
            os.rmdir(outside)

    def test_resolve_file_accepts_inside_and_rejects_escape(self):
        nested = self.root / 'in'
        nested.mkdir()
        book = nested / 'book.epub'
        book.write_bytes(b'epub')
        self.assertEqual(
            self.ws.resolve_file('in/book.epub', must_exist=True), book)
        self.assertEqual(
            self.ws.resolve_file(str(book), must_exist=True), book)
        with self.assertRaises(PathError):
            self.ws.resolve_file('../book.epub', must_exist=False)
        with self.assertRaises(PathError):
            self.ws.resolve_file('in/missing.epub', must_exist=True)

    def test_resolve_file_rejects_absolute_outside_root(self):
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other).resolve() / 'book.epub'
            outside.write_bytes(b'epub')
            with self.assertRaises(PathError):
                self.ws.resolve_file(str(outside), must_exist=False)

    def test_temp_dir_requires_single_component(self):
        (self.root / 'ok_temp').mkdir()
        self.assertTrue(self.ws.temp_dir('ok_temp').is_dir())
        for bad in ('../evil', 'sub/dir', 'a\\b', '', '.', '..', 'ok_temp/../ok2'):
            with self.assertRaises(PathError):
                self.ws.temp_dir(bad)

    def test_chunk_file_kinds(self):
        temp = self.root / 'book_temp'
        temp.mkdir()
        self.assertEqual(
            self.ws.chunk_file(temp, 'chunk0001.md'),
            temp / 'chunk0001.md',
        )
        self.assertEqual(
            self.ws.chunk_file(temp, 'output_chunk0001.md', kind='output'),
            temp / 'output_chunk0001.md',
        )
        self.assertEqual(
            self.ws.chunk_file(temp, 'output_chunk0001.meta.json', kind='meta'),
            temp / 'output_chunk0001.meta.json',
        )
        for name, kind in (
            ('chunk1.md', 'source'),
            ('chunk0001.txt', 'source'),
            ('chunk0001.md', 'output'),
            ('output_chunk0001.md', 'source'),
            ('output_chunk0001.meta.json', 'output'),
            ('output_chunk0001.md.meta.json', 'meta'),
        ):
            with self.assertRaises(PathError, msg=f'{name}/{kind}'):
                self.ws.chunk_file(temp, name, kind=kind)

    def test_workspace_root_must_exist(self):
        with self.assertRaises(PathError):
            Workspace(self.root / 'missing_dir')


if __name__ == '__main__':
    unittest.main()
