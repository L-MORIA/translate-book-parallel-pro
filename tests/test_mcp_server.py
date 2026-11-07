"""Protocol-level tests for the MCP stdio server (stdlib JSON-RPC, no SDK).

Exercises the wire format end to end through serve() with injected pipes:
handshake, tools, resources, prompts, and the error/notification semantics.
"""

import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for p in (REPO_ROOT, REPO_ROOT / 'scripts'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import manifest  # noqa: E402

from translate_book_mcp import server as mcp_server  # noqa: E402
from translate_book_mcp.paths import Workspace  # noqa: E402


class ServerTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.book = self.root / 'book_temp'
        self.book.mkdir()
        (self.book / 'chunk0001.md').write_text('Source text.', encoding='utf-8')
        (self.book / 'input.md').write_text('combined', encoding='utf-8')
        manifest.create_manifest(str(self.book), ['chunk0001.md'],
                                 str(self.book / 'input.md'))

    def tearDown(self):
        self._tmp.cleanup()

    def converse(self, *messages):
        """Run serve() over in-memory pipes; return parsed responses."""
        fin = StringIO('\n'.join(json.dumps(m) for m in messages) + '\n')
        fout = StringIO()
        mcp_server.serve(self.root, stdin=fin, stdout=fout)
        return [json.loads(line) for line in fout.getvalue().splitlines()]

    def one(self, *messages):
        return self.converse(*messages)[0]

    def rpc(self, msg_id, method, params=None):
        msg = {'jsonrpc': '2.0', 'id': msg_id, 'method': method}
        if params is not None:
            msg['params'] = params
        return msg

    # -- lifecycle ----------------------------------------------------------

    def test_initialize_echoes_client_protocol_version(self):
        resp = self.one(self.rpc(1, 'initialize', {
            'protocolVersion': '2024-11-05',
            'capabilities': {},
        }))
        self.assertEqual(resp['result']['protocolVersion'], '2024-11-05')
        self.assertEqual(
            resp['result']['serverInfo']['name'], 'translate-book-parallel-pro')
        self.assertIn('tools', resp['result']['capabilities'])

    def test_ping_returns_empty_result(self):
        resp = self.one(self.rpc(2, 'ping'))
        self.assertEqual(resp['result'], {})

    def test_initialized_notification_gets_no_response(self):
        msgs = [
            self.rpc(1, 'initialize', {'protocolVersion': '2024-11-05'}),
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        ]
        responses = self.converse(*msgs)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]['id'], 1)

    def test_blank_lines_are_skipped(self):
        fin = StringIO('\n\n' + json.dumps(self.rpc(1, 'ping')) + '\n\n')
        fout = StringIO()
        mcp_server.serve(self.root, stdin=fin, stdout=fout)
        self.assertEqual(len(fout.getvalue().splitlines()), 1)

    def test_parse_error_returns_id_null(self):
        fin = StringIO('not json\n')
        fout = StringIO()
        mcp_server.serve(self.root, stdin=fin, stdout=fout)
        resp = json.loads(fout.getvalue())
        self.assertIsNone(resp['id'])
        self.assertEqual(resp['error']['code'], -32700)

    def test_non_object_request_rejected(self):
        fin = StringIO('[1, 2, 3]\n')
        fout = StringIO()
        mcp_server.serve(self.root, stdin=fin, stdout=fout)
        resp = json.loads(fout.getvalue())
        self.assertEqual(resp['error']['code'], -32600)

    def test_unknown_method_reports_method_not_found(self):
        resp = self.one(self.rpc(9, 'bookmarks/list'))
        self.assertEqual(resp['error']['code'], -32601)

    def test_unknown_notification_is_silently_ignored(self):
        responses = self.converse({'jsonrpc': '2.0', 'method': 'x/unknown'})
        self.assertEqual(responses, [])

    # -- tools --------------------------------------------------------------

    def test_tools_list_exposes_eight_mvp_tools(self):
        resp = self.one(self.rpc(3, 'tools/list'))
        names = [t['name'] for t in resp['result']['tools']]
        self.assertEqual(names, [
            'convert_book', 'get_status', 'get_translation_plan',
            'get_chunk_prompt', 'submit_translation', 'merge_meta',
            'validate_book', 'build_book',
        ])
        for tool in resp['result']['tools']:
            self.assertIn('inputSchema', tool)
            self.assertIn('description', tool)

    def test_tools_call_get_status(self):
        resp = self.one(self.rpc(4, 'tools/call', {
            'name': 'get_status',
            'arguments': {'temp_dir': str(self.book)},
        }))
        self.assertFalse(resp['result']['isError'])
        payload = json.loads(resp['result']['content'][0]['text'])
        self.assertEqual(payload['source_chunks'], 1)

    def test_tools_call_unknown_tool(self):
        resp = self.one(self.rpc(5, 'tools/call', {'name': 'nope'}))
        self.assertEqual(resp['error']['code'], -32602)

    def test_tools_call_path_error_is_a_clean_tool_error(self):
        resp = self.one(self.rpc(6, 'tools/call', {
            'name': 'get_chunk_prompt',
            'arguments': {'temp_dir': str(self.book), 'chunk_id': 'chunk1',
                          'target_language': 'Russian'},
        }))
        self.assertEqual(resp['error']['code'], -32000)
        self.assertIn('chunk0001', resp['error']['message'])

    def test_tools_call_submit_then_plan_sees_it(self):
        submit = self.one(self.rpc(7, 'tools/call', {
            'name': 'submit_translation',
            'arguments': {
                'temp_dir': str(self.book), 'chunk_id': 'chunk0001',
                'content': 'Перевод исходного текста.',
            },
        }))
        self.assertFalse(submit['result']['isError'])
        payload = json.loads(submit['result']['content'][0]['text'])
        self.assertTrue(payload['output_path'].endswith('output_chunk0001.md'))
        self.assertEqual(payload['warnings'], [])

        plan = self.one(self.rpc(8, 'tools/call', {
            'name': 'get_translation_plan',
            'arguments': {'temp_dir': str(self.book)},
        }))
        plan_payload = json.loads(plan['result']['content'][0]['text'])
        self.assertNotIn('chunk0001', plan_payload['translation_chunk_ids'])

    def test_tools_call_escapes_workspace(self):
        resp = self.one(self.rpc(10, 'tools/call', {
            'name': 'get_status',
            'arguments': {'temp_dir': '../outside_temp'},
        }))
        self.assertEqual(resp['error']['code'], -32000)

    # -- resources ----------------------------------------------------------

    def test_resources_list_and_read_manifest(self):
        listing = self.one(self.rpc(11, 'resources/list'))
        uris = [r['uri'] for r in listing['result']['resources']]
        self.assertIn(f'translate-book://temp/book_temp/manifest', uris)

        read = self.one(self.rpc(12, 'resources/read', {
            'uri': 'translate-book://temp/book_temp/manifest',
        }))
        self.assertEqual(read['result']['contents'][0]['mimeType'],
                         'text/plain; charset=utf-8')
        body = json.loads(read['result']['contents'][0]['text'])
        self.assertEqual(body['chunk_count'], 1)

    def test_resources_read_chunk_content(self):
        read = self.one(self.rpc(13, 'resources/read', {
            'uri': 'translate-book://temp/book_temp/chunks/chunk0001',
        }))
        self.assertEqual(read['result']['contents'][0]['text'], 'Source text.')

    def test_resources_read_unknown_uri(self):
        resp = self.one(self.rpc(14, 'resources/read', {'uri': 'translate-book://x'}))
        self.assertEqual(resp['error']['code'], -32602)

    def test_resources_read_missing_file(self):
        resp = self.one(self.rpc(15, 'resources/read', {
            'uri': 'translate-book://temp/book_temp/output/chunk0001',
        }))
        self.assertEqual(resp['error']['code'], -32002)  # valid id, no output yet

    def test_resources_read_rejects_bad_names(self):
        bad = self.one(self.rpc(17, 'resources/read', {
            'uri': 'translate-book://temp/book_temp/output/../chunk0001.md',
        }))
        self.assertEqual(bad['error']['code'], -32602)

    # -- prompts ------------------------------------------------------------

    def test_prompts_list_and_get(self):
        listing = self.one(self.rpc(18, 'prompts/list'))
        names = [p['name'] for p in listing['result']['prompts']]
        self.assertEqual(names, ['translate_chunk', 'review_translation'])

        got = self.one(self.rpc(19, 'prompts/get', {
            'name': 'translate_chunk',
            'arguments': {'temp_dir': str(self.book), 'chunk_id': 'chunk0001',
                          'target_language': 'Russian'},
        }))
        message = got['result']['messages'][0]
        self.assertEqual(message['role'], 'user')
        self.assertIn('Переведите файл-источник', message['content']['text'])

    def test_prompts_get_unknown_name(self):
        resp = self.one(self.rpc(20, 'prompts/get', {'name': 'nope'}))
        self.assertEqual(resp['error']['code'], -32602)


if __name__ == '__main__':
    unittest.main()
