"""Tool-level tests for the MCP server (no LLM, no external tools).

convert_book / build_book mock scripts/_run_python; everything else runs
against real fixture temp directories built with manifest.create_manifest.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import manifest  # noqa: E402

from translate_book_mcp import tools  # noqa: E402
from translate_book_mcp.paths import PathError, Workspace  # noqa: E402
from translate_book_mcp import prompts  # noqa: E402


def _glossary(*pairs):
    terms = [
        {
            'id': src, 'source': src, 'target': tgt, 'category': '',
            'aliases': [], 'gender': 'unknown', 'confidence': 'medium',
            'frequency': 0, 'evidence_refs': [], 'notes': '',
        }
        for src, tgt in pairs
    ]
    return {'version': 2, 'terms': terms, 'high_frequency_top_n': 20,
            'applied_meta_hashes': {}}


class FixtureBook:
    """A temp dir with two chunks and a manifest built by the real creator."""

    def __init__(self, root):
        self.root = Path(root)
        self.temp = self.root / 'book_temp'
        self.temp.mkdir()
        (self.temp / 'chunk0001.md').write_text(
            'Alice was beginning to get very tired. ' * 3, encoding='utf-8')
        (self.temp / 'chunk0002.md').write_text(
            'So she was considering in her own mind. ' * 3, encoding='utf-8')
        (self.temp / 'input.md').write_text('combined source', encoding='utf-8')
        manifest.create_manifest(
            str(self.temp), ['chunk0001.md', 'chunk0002.md'],
            str(self.temp / 'input.md'),
        )


class ToolsTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.ws = Workspace(self.root)
        self.book = FixtureBook(self.root)

    def tearDown(self):
        self._tmp.cleanup()


class GetChunkPromptTests(ToolsTestCase):
    def test_prompt_without_glossary_omits_rule13_and_reports_paths(self):
        result = tools.get_chunk_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'target_language': 'Russian',
        })
        self.assertNotIn('13.', result['prompt'])
        self.assertFalse(result['term_table_present'])
        self.assertTrue(result['source_path'].endswith('chunk0001.md'))
        self.assertTrue(result['output_path'].endswith('output_chunk0001.md'))
        self.assertTrue(result['meta_path'].endswith('output_chunk0001.meta.json'))
        # chunk0001 has no previous neighbor, only a next one
        self.assertTrue(result['neighbor_context_present'])

    def test_prompt_with_glossary_injects_term_table(self):
        data = _glossary(('Alice', 'Алиса'))
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(data), encoding='utf-8')
        result = tools.get_chunk_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0002',
            'target_language': 'Russian',
        })
        self.assertTrue(result['term_table_present'])
        self.assertIn('Alice', result['prompt'])
        self.assertIn('Алиса', result['prompt'])

    def test_invalid_chunk_id_rejected(self):
        for bad in ('chunk1', 'chunk00001', '../chunk0001', ''):
            with self.assertRaises(PathError, msg=bad):
                tools.get_chunk_prompt(self.ws, {
                    'temp_dir': str(self.book.temp), 'chunk_id': bad,
                    'target_language': 'Russian',
                })

    def test_missing_source_chunk_raises_clean_error(self):
        with self.assertRaises(tools.ToolError):
            tools.get_chunk_prompt(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk9999',
                'target_language': 'Russian',
            })


class SubmitTranslationTests(ToolsTestCase):
    def test_writes_output_and_meta_with_hash(self):
        result = tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content': '# Алиса в Зазеркалье\n\nПереведённый текст.',
            'meta': {'schema_version': 1, 'new_entities': [],
                     'alias_hypotheses': [], 'attribute_hypotheses': [],
                     'used_term_sources': [], 'conflicts': []},
        })
        out = self.book.temp / 'output_chunk0001.md'
        self.assertTrue(out.is_file())
        self.assertEqual(out.read_text(encoding='utf-8'),
                         '# Алиса в Зазеркалье\n\nПереведённый текст.')
        meta = json.loads(
            (self.book.temp / 'output_chunk0001.meta.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['schema_version'], 1)
        self.assertEqual(result['bytes'], out.stat().st_size)
        self.assertEqual(result['sha256'], manifest.file_hash(str(out)))
        self.assertEqual(result['warnings'], [])

    def test_empty_content_rejected(self):
        for bad in ('', '   ', None, 123):
            with self.assertRaises(tools.ToolError, msg=repr(bad)):
                tools.submit_translation(self.ws, {
                    'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                    'content': bad,
                })

    def test_meta_with_chunk_id_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.submit_translation(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'content': 'text', 'meta': {'chunk_id': 'chunk0001'},
            })

    def test_suspiciously_short_output_warns(self):
        # the gate only fires on substantial sources (> 1000 chars)
        long_source = 'She was considering in her own mind whether the pleasure ' * 25
        (self.book.temp / 'chunk0002.md').write_text(long_source, encoding='utf-8')
        result = tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0002',
            'content': 'x',
        })
        self.assertTrue(result['warnings'])


class GetTranslationPlanTests(ToolsTestCase):
    def test_missing_output_is_action_translate(self):
        plan = tools.get_translation_plan(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertIn('chunk0001', plan['translation_chunk_ids'])
        self.assertIn('chunk0002', plan['translation_chunk_ids'])

    def test_translated_chunk_is_recorded_or_unchanged_side(self):
        (self.book.temp / 'output_chunk0001.md').write_text(
            'Перевод первого чанка, достаточно длинный. ' * 3, encoding='utf-8')
        plan = tools.get_translation_plan(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertNotIn('chunk0001', plan['translation_chunk_ids'])
        self.assertIn('chunk0002', plan['translation_chunk_ids'])


class ValidateBookTests(ToolsTestCase):
    def test_incomplete_book_fails_the_gate(self):
        result = tools.validate_book(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertFalse(result['ok'])
        self.assertIsNone(result['output_files'])

    def test_complete_book_passes_the_gate(self):
        (self.book.temp / 'output_chunk0001.md').write_text('перевод 1', encoding='utf-8')
        (self.book.temp / 'output_chunk0002.md').write_text('перевод 2', encoding='utf-8')
        result = tools.validate_book(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['output_files']), 2)

    def test_library_prints_are_captured_into_logs(self):
        result = tools.validate_book(self.ws, {'temp_dir': str(self.book.temp)})
        # validate_for_merge prints its errors; the capture must keep them out
        # of the real stdout and inside the structured result instead.
        self.assertTrue(result['logs'])
        self.assertTrue(any('ERROR' in line for line in result['logs']))


class ConvertBookTests(ToolsTestCase):
    def test_success_returns_temp_dir_and_chunk_count(self):
        def fake_run(script, *argv, cwd=None):
            self.assertEqual(script, 'convert.py')
            self.assertIn('--olang', argv)
            self.assertIn('ru', argv)
            out = ('Created manifest.json (1 chunks)\n'
                   f'Temp directory: {self.root / "newbook_temp"}\n'
                   'Conversion completed successfully!')
            return 0, out, ''

        (self.root / 'newbook_temp').mkdir()
        manifest.create_manifest(
            str(self.root / 'newbook_temp'), ['chunk0001.md'],
            str(self.root / 'input.md'),
        )
        src = self.root / 'book.epub'
        src.write_bytes(b'epub')
        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.convert_book(self.ws, {
                'input_file': str(src), 'output_lang': 'ru',
            })
        self.assertEqual(result['temp_id'], 'newbook_temp')
        # convert picks the newest *_temp dir — the one this run just made
        self.assertEqual(result['chunk_count'], 1)

    def test_nonzero_exit_raises_clean_error(self):
        src = self.root / 'book.epub'
        src.write_bytes(b'epub')
        with mock.patch.object(tools, '_run_python', return_value=(1, '', 'boom')):
            with self.assertRaises(tools.ToolError) as ctx:
                tools.convert_book(self.ws, {'input_file': str(src)})
        self.assertIn('convert.py failed', str(ctx.exception))

    def test_missing_input_file_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.convert_book(self.ws, {'input_file': str(self.root / 'no.epub')})

    def test_input_outside_workspace_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            src = Path(other) / 'book.epub'
            src.write_bytes(b'epub')
            with self.assertRaises(PathError):
                tools.convert_book(self.ws, {'input_file': str(src)})


class BuildBookTests(ToolsTestCase):
    def test_success_reports_output_sizes(self):
        (self.book.temp / 'output_chunk0001.md').write_text('п1', encoding='utf-8')
        (self.book.temp / 'output_chunk0002.md').write_text('п2', encoding='utf-8')
        for name in ('book.html', 'book.docx', 'book.epub', 'book.pdf'):
            (self.book.temp / name).write_bytes(b'x' * 11)

        captured = {}

        def fake_run(script, *argv, cwd=None):
            captured['argv'] = argv
            self.assertEqual(script, 'merge_and_build.py')
            self.assertIn(str(self.book.temp), argv)
            return 0, 'Build Complete', ''

        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.build_book(self.ws, {
                'temp_dir': str(self.book.temp), 'title': 'Тест',
            })
        self.assertIn('--title', captured['argv'])
        self.assertEqual(result['outputs']['book.epub']['bytes'], 11)
        self.assertEqual(set(result['outputs']), set(tools.BOOK_FORMATS))

    def test_nonzero_exit_raises_clean_error(self):
        with mock.patch.object(tools, '_run_python', return_value=(1, '', 'boom')):
            with self.assertRaises(tools.ToolError):
                tools.build_book(self.ws, {'temp_dir': str(self.book.temp)})


class MergeMetaTests(ToolsTestCase):
    def test_no_glossary_is_a_documented_noop(self):
        result = tools.merge_meta(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertEqual(result['status'], 'no_glossary')
        self.assertEqual(result['auto_apply'], [])

    def test_prepare_parses_proposal(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        proposal = {'auto_apply': [{'source': 'Alice'}], 'decisions_needed': []}

        with mock.patch.object(
            tools, '_run_python',
            return_value=(0, json.dumps(proposal), ''),
        ) as run:
            result = tools.merge_meta(self.ws, {'temp_dir': str(self.book.temp)})
        run.assert_called_once()
        self.assertEqual(result['auto_apply'][0]['source'], 'Alice')
        self.assertFalse(result['applied'])

    def test_apply_without_decisions_rejected(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        with mock.patch.object(
            tools, '_run_python', return_value=(0, '{"auto_apply": []}', ''),
        ):
            with self.assertRaises(tools.ToolError):
                tools.merge_meta(self.ws, {
                    'temp_dir': str(self.book.temp), 'apply': True,
                })


class PromptTests(unittest.TestCase):
    def test_ru_template_selected_for_russian(self):
        p = prompts.build_chunk_prompt('a.md', 'b.md', 'c.json', 'Russian')
        self.assertIn('Переведите файл-источник', p)
        self.assertIn('Строго сохраняйте Markdown-разметку', p)

    def test_generic_template_for_other_languages(self):
        p = prompts.build_chunk_prompt('a.md', 'b.md', 'c.json', 'English')
        self.assertIn('Translate the source file', p)
        self.assertIn('Preserve Markdown structure', p)

    def test_rule13_included_only_with_term_table(self):
        base = dict(source_path='a.md', output_path='b.md', meta_path='c.json',
                    target_language='ru', neighbor_context='')
        without = prompts.build_chunk_prompt(term_table='', **base)
        self.assertNotIn('Единообразие терминов', without)
        with_table = prompts.build_chunk_prompt(
            term_table='| 原文 | 别名 | 译文 |\n|---|---|---|\n| Alice | | Алиса |',
            **base)
        self.assertIn('Единообразие терминов', with_table)
        self.assertIn('Алиса', with_table)

    def test_neighbor_context_included_only_when_present(self):
        base = dict(source_path='a.md', output_path='b.md', meta_path='c.json',
                    target_language='ru', term_table='')
        without = prompts.build_chunk_prompt(neighbor_context='', **base)
        self.assertNotIn('Контекст соседних фрагментов', without)
        with_ctx = prompts.build_chunk_prompt(
            neighbor_context='Next chunk excerpt (chunk0002.md, read-only):\n```text\n…\n```',
            **base)
        self.assertIn('Контекст соседних фрагментов', with_ctx)


class PromptSyncTests(unittest.TestCase):
    """Guard against drift between the SKILL.md templates and prompts.py."""

    def test_ru_rules_match_skill_md_marker(self):
        skill = (REPO_ROOT / 'SKILL.md').read_text(encoding='utf-8')
        for marker in ('Строго сохраняйте Markdown-разметку',
                       'Выводите ТОЛЬКО переведённый текст'):
            self.assertIn(marker, skill)
            self.assertIn(marker, prompts.RU_RULES)

    def test_review_prompt_mentions_output_and_source(self):
        p = prompts.build_review_prompt('src.md', 'out.md', 'Russian')
        self.assertIn('src.md', p)
        self.assertIn('out.md', p)


if __name__ == '__main__':
    unittest.main()
