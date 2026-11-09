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
        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
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

    def test_default_output_lang_matches_convert_cli(self):
        (self.root / 'newbook_temp').mkdir()
        manifest.create_manifest(
            str(self.root / 'newbook_temp'), ['chunk0001.md'],
            str(self.root / 'input.md'),
        )
        src = self.root / 'book.epub'
        src.write_bytes(b'epub')
        out = f'Temp directory: {self.root / "newbook_temp"}'
        with mock.patch.object(tools, '_run_python',
                               return_value=(0, out, '')) as run:
            tools.convert_book(self.ws, {'input_file': str(src)})
        argv = run.call_args.args[1:]
        self.assertEqual(argv[argv.index('--olang') + 1], 'zh')

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

        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
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


class ConvertBookOptionsTests(ToolsTestCase):
    def _fixture(self, lang='ru'):
        (self.root / 'newbook_temp').mkdir()
        (self.root / 'newbook_temp' / 'chunk0001.md').write_text(
            'source', encoding='utf-8')
        manifest.create_manifest(
            str(self.root / 'newbook_temp'), ['chunk0001.md'],
            str(self.root / 'input.md'),
        )
        (self.root / 'newbook_temp' / 'config.txt').write_text(
            f'output_lang={lang}\n', encoding='utf-8')
        src = self.root / 'book.epub'
        src.write_bytes(b'epub')
        return src

    def test_strip_page_numbers_and_chunk_ids_are_reported(self):
        src = self._fixture()
        captured = {}

        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
            captured['argv'] = argv
            return 0, f'Temp directory: {self.root / "newbook_temp"}', ''

        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.convert_book(self.ws, {
                'input_file': str(src), 'output_lang': 'ru',
                'strip_page_numbers': True,
            })
        self.assertIn('--strip-page-numbers', captured['argv'])
        self.assertEqual(result['chunk_ids'], ['chunk0001'])
        self.assertEqual(result['output_lang'], 'ru')

    def test_chunk_size_and_extension_are_validated(self):
        src = self._fixture()
        for bad in (100, 1_000_001, True, 'abc'):
            with self.assertRaises(tools.ToolError, msg=repr(bad)):
                tools.convert_book(self.ws, {
                    'input_file': str(src), 'chunk_size': bad,
                })
        txt = self.root / 'book.txt'
        txt.write_text('not a book', encoding='utf-8')
        with self.assertRaises(tools.ToolError):
            tools.convert_book(self.ws, {'input_file': str(txt)})

    def test_temp_root_is_created(self):
        src = self._fixture()
        out_root = self.root / 'nested' / 'out'
        temp = out_root / 'newbook_temp'
        temp.mkdir(parents=True)
        (temp / 'chunk0001.md').write_text('source', encoding='utf-8')
        manifest.create_manifest(
            str(temp), ['chunk0001.md'], str(temp / 'input.md'))

        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
            return 0, f'Temp directory: {temp}', ''

        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.convert_book(self.ws, {
                'input_file': str(src), 'temp_root': str(out_root),
            })
        self.assertEqual(result['temp_id'], 'newbook_temp')


class GetChunkPromptOptionsTests(ToolsTestCase):
    def test_language_code_uses_config_fallback_and_is_mapped(self):
        (self.book.temp / 'config.txt').write_text(
            'output_lang=ru\n', encoding='utf-8')
        result = tools.get_chunk_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
        })
        self.assertEqual(result['target_language_input'], 'ru')
        self.assertEqual(result['target_language'], 'Russian')
        self.assertIn('на Russian', result['prompt'])

    def test_custom_instructions_and_glossary_numbering(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        result = tools.get_chunk_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'target_language': 'ru',
            'custom_instructions': 'Keep footnotes verbatim',
        })
        self.assertIn('12. Keep footnotes verbatim', result['prompt'])
        self.assertIn('13. Единообразие терминов', result['prompt'])
        self.assertTrue(result['selected_term_ids'])
        self.assertEqual(len(result['glossary_hash']), 64)

    def test_source_text_and_metadata_are_optional(self):
        result = tools.get_chunk_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'target_language': 'Russian', 'include_source_text': True,
        })
        self.assertIn('Alice', result['source_text'])
        self.assertEqual(len(result['source_sha256']), 64)
        self.assertEqual(result['char_count'], len(result['source_text']))
        self.assertIn('schema_version', result['meta_schema'])
        self.assertNotIn('Markdown source text:', result['prompt'])

    def test_invalid_top_n_is_rejected(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        with self.assertRaises(tools.ToolError):
            tools.get_chunk_prompt(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'target_language': 'ru', 'top_n': 'many',
            })


class SubmitTranslationOptionsTests(ToolsTestCase):
    def test_content_path_writes_output_synthetic_meta_and_records(self):
        handoff = self.root / 'handoff.md'
        handoff.write_text('Перевод через файл.', encoding='utf-8')
        result = tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content_path': str(handoff),
        })
        self.assertEqual(
            (self.book.temp / 'output_chunk0001.md').read_text(encoding='utf-8'),
            'Перевод через файл.',
        )
        self.assertTrue(result['meta_synthetic'])
        self.assertTrue(result['recorded'])
        meta = json.loads(
            (self.book.temp / 'output_chunk0001.meta.json').read_text(
                encoding='utf-8'))
        self.assertEqual(meta['schema_version'], 1)
        plan = tools.get_translation_plan(
            self.ws, {'temp_dir': str(self.book.temp)})
        self.assertNotIn('chunk0001', plan['translation_chunk_ids'])
        self.assertNotIn('chunk0001', plan['record_only_chunk_ids'])

    def test_content_and_content_path_are_mutually_exclusive(self):
        handoff = self.root / 'handoff.md'
        handoff.write_text('text', encoding='utf-8')
        with self.assertRaises(tools.ToolError):
            tools.submit_translation(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'content': 'text', 'content_path': str(handoff),
            })

    def test_content_path_cannot_be_the_source_chunk(self):
        with self.assertRaises(tools.ToolError):
            tools.submit_translation(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'content_path': str(self.book.temp / 'chunk0001.md'),
            })

    def test_nul_and_oversize_content_are_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.submit_translation(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'content': 'bad\x00text',
            })
        with mock.patch.object(tools, 'MAX_TRANSLATION_CHARS', 10):
            with self.assertRaises(tools.ToolError):
                tools.submit_translation(self.ws, {
                    'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                    'content': 'x' * 11,
                })

    def test_meta_schema_is_validated_strictly(self):
        with self.assertRaises(tools.ToolError):
            tools.submit_translation(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
                'content': 'text', 'meta': {'schema_version': 1,
                                            'new_entities': 'bad'},
            })

    def test_record_false_leaves_chunk_in_record_only_plan(self):
        result = tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content': 'Перевод без записи в run_state.', 'record': False,
        })
        self.assertFalse(result['recorded'])
        plan = tools.get_translation_plan(
            self.ws, {'temp_dir': str(self.book.temp)})
        self.assertIn('chunk0001', plan['record_only_chunk_ids'])

    def test_existing_meta_is_preserved_when_meta_is_omitted(self):
        meta = {
            'schema_version': 1, 'new_entities': [], 'alias_hypotheses': [],
            'attribute_hypotheses': [], 'used_term_sources': [], 'conflicts': [],
        }
        meta_path = self.book.temp / 'output_chunk0001.meta.json'
        meta_path.write_text(json.dumps(meta), encoding='utf-8')
        result = tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content': 'text',
        })
        self.assertFalse(result['meta_written'])
        self.assertFalse(result['meta_synthetic'])
        self.assertEqual(json.loads(meta_path.read_text(encoding='utf-8')), meta)

    def test_atomic_write_leaves_no_temp_files(self):
        tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content': 'text',
        })
        self.assertEqual(list(self.book.temp.glob('.mcp-*.tmp')), [])


class GetStatusOptionsTests(ToolsTestCase):
    def test_status_reports_config_chunks_glossary_meta_and_outputs(self):
        (self.book.temp / 'config.txt').write_text(
            'output_lang=ru\n', encoding='utf-8')
        (self.book.temp / 'output_chunk0001.md').write_text(
            'перевод', encoding='utf-8')
        (self.book.temp / 'output_chunk0001.meta.json').write_text(
            json.dumps({
                'schema_version': 1, 'new_entities': [],
                'alias_hypotheses': [], 'attribute_hypotheses': [],
                'used_term_sources': [], 'conflicts': [],
            }), encoding='utf-8')
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        (self.book.temp / 'book.html').write_text('<html>', encoding='utf-8')

        status = tools.get_status(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertEqual(status['config']['output_lang'], 'ru')
        self.assertEqual(status['chunks']['total'], 2)
        self.assertEqual(status['chunks']['translated'], 1)
        self.assertIn('chunk0002', status['chunks']['missing_output_chunk_ids'])
        self.assertEqual(status['outputs_present'], 1)
        self.assertTrue(status['glossary']['present'])
        self.assertEqual(status['glossary']['term_count'], 1)
        self.assertEqual(len(status['glossary']['hash']), 64)
        self.assertEqual(status['meta']['status']['meta_files_found'], 1)
        self.assertIn('book.html', [o['file'] for o in status['outputs']])
        self.assertIsInstance(status['logs'], list)

    def test_corrupt_manifest_is_reported_not_fatal(self):
        (self.book.temp / 'manifest.json').write_text('{bad', encoding='utf-8')
        status = tools.get_status(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertTrue(status['manifest']['exists'])
        self.assertTrue(status['manifest']['error'])
        self.assertEqual(status['chunks']['total'], 0)

    def test_no_glossary_skips_meta_status(self):
        status = tools.get_status(self.ws, {'temp_dir': str(self.book.temp)})
        self.assertFalse(status['glossary']['present'])
        self.assertIsNone(status['meta']['status'])


class GetTranslationPlanOptionsTests(ToolsTestCase):
    def test_include_chunks_false_and_next_chunk_id(self):
        plan = tools.get_translation_plan(self.ws, {
            'temp_dir': str(self.book.temp), 'include_chunks': False,
        })
        self.assertNotIn('chunks', plan)
        self.assertEqual(plan['next_chunk_id'], 'chunk0001')

    def test_next_chunk_id_moves_after_submit(self):
        tools.submit_translation(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
            'content': 'перевод',
        })
        plan = tools.get_translation_plan(
            self.ws, {'temp_dir': str(self.book.temp)})
        self.assertEqual(plan['next_chunk_id'], 'chunk0002')


class MergeMetaOptionsTests(ToolsTestCase):
    def test_status_action_returns_report(self):
        report = {'translated_chunks': 0, 'meta_files_found': 0}
        with mock.patch.object(
            tools, '_run_python',
            return_value=(0, json.dumps(report), ''),
        ):
            result = tools.merge_meta(self.ws, {
                'temp_dir': str(self.book.temp), 'action': 'status',
            })
        self.assertEqual(result['action'], 'status')
        self.assertEqual(result['report'], report)

    def test_apply_action_sends_decisions_on_stdin(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        decisions = {'decisions': [], 'auto_apply': []}
        captured = {}

        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
            captured['argv'] = argv
            captured['input'] = input_text
            return 0, json.dumps({'applied': 0}), ''

        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.merge_meta(self.ws, {
                'temp_dir': str(self.book.temp), 'action': 'apply',
                'decisions': decisions,
            })
        self.assertIn('apply-merge', captured['argv'])
        self.assertEqual(json.loads(captured['input']), decisions)
        self.assertTrue(result['applied'])

    def test_decisions_size_limit(self):
        (self.book.temp / 'glossary.json').write_text(
            json.dumps(_glossary(('Alice', 'Алиса'))), encoding='utf-8')
        with mock.patch.object(tools, 'MAX_DECISIONS_BYTES', 5):
            with self.assertRaises(tools.ToolError):
                tools.merge_meta(self.ws, {
                    'temp_dir': str(self.book.temp), 'action': 'apply',
                    'decisions': {'decisions': []},
                })

    def test_invalid_action_rejected(self):
        with self.assertRaises(tools.ToolError):
            tools.merge_meta(self.ws, {
                'temp_dir': str(self.book.temp), 'action': 'explode',
            })


class BuildBookOptionsTests(ToolsTestCase):
    def test_cover_export_and_cleanup_flags(self):
        (self.book.temp / 'output_chunk0001.md').write_text('п1', encoding='utf-8')
        (self.book.temp / 'output_chunk0002.md').write_text('п2', encoding='utf-8')
        (self.book.temp / 'output.md').write_text('# book', encoding='utf-8')
        (self.book.temp / 'book_doc.html').write_text('<html>', encoding='utf-8')
        cover = self.root / 'cover.png'
        cover.write_bytes(b'\x89PNG')
        captured = {}

        def fake_run(script, *argv, cwd=None, input_text=None, timeout=None):
            captured['argv'] = argv
            return 0, 'Build Complete', ''

        with mock.patch.object(tools, '_run_python', side_effect=fake_run):
            result = tools.build_book(self.ws, {
                'temp_dir': str(self.book.temp), 'cover': str(cover),
                'export_name': 'alice-ru', 'cleanup': True,
                'cleanup_translations': True,
            })
        self.assertIn('--cover', captured['argv'])
        self.assertIn(str(cover), captured['argv'])
        self.assertIn('--export-name', captured['argv'])
        self.assertIn('alice-ru', captured['argv'])
        self.assertIn('--cleanup', captured['argv'])
        self.assertIn('--cleanup-translations', captured['argv'])
        self.assertIn('output.md', [a['file'] for a in result['artifacts']])

    def test_cleanup_translations_requires_cleanup(self):
        with self.assertRaises(tools.ToolError):
            tools.build_book(self.ws, {
                'temp_dir': str(self.book.temp),
                'cleanup_translations': True,
            })

    def test_cover_outside_workspace_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            cover = Path(other) / 'cover.png'
            cover.write_bytes(b'png')
            with self.assertRaises(PathError):
                tools.build_book(self.ws, {
                    'temp_dir': str(self.book.temp), 'cover': str(cover),
                })


class ReviewPromptOptionsTests(ToolsTestCase):
    def test_review_prompt_uses_config_language(self):
        (self.book.temp / 'config.txt').write_text(
            'output_lang=ru\n', encoding='utf-8')
        result = tools.review_prompt(self.ws, {
            'temp_dir': str(self.book.temp), 'chunk_id': 'chunk0001',
        })
        self.assertEqual(result['target_language'], 'Russian')
        self.assertIn('Проверьте перевод', result['prompt'])

    def test_review_prompt_rejects_bad_chunk_id(self):
        with self.assertRaises(PathError):
            tools.review_prompt(self.ws, {
                'temp_dir': str(self.book.temp), 'chunk_id': 'chunk1',
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

    def test_language_codes_are_mapped_to_names(self):
        self.assertEqual(prompts.language_name('ru'), 'Russian')
        self.assertEqual(prompts.language_name('ZH'), 'Chinese')
        self.assertEqual(prompts.language_name('klingon'), 'klingon')
        self.assertEqual(prompts.language_name(''), 'Chinese')
        self.assertTrue(prompts.is_russian('русский'))
        self.assertFalse(prompts.is_russian('en'))
        p = prompts.build_chunk_prompt(
            'a.md', 'b.md', 'c.json', 'ru', term_table='')
        self.assertIn('на Russian', p)

    def test_custom_instructions_become_rule_12(self):
        p = prompts.build_chunk_prompt(
            'a.md', 'b.md', 'c.json', 'ru',
            custom_instructions='Keep footnotes verbatim',
        )
        self.assertIn('12. Keep footnotes verbatim', p)
        self.assertNotIn('13.', p)

    def test_meta_schema_template_covers_all_arrays(self):
        schema = prompts.meta_schema_template()
        self.assertEqual(schema['schema_version'], 1)
        for key in ('new_entities', 'alias_hypotheses',
                    'attribute_hypotheses', 'used_term_sources', 'conflicts'):
            self.assertIn(key, schema)


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
