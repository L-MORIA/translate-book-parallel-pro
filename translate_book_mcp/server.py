"""Minimal MCP stdio server for the translate-book pipeline (ROADMAP.md P0).

Implements the MCP stdio transport with the standard library only —
newline-delimited JSON-RPC 2.0 over stdin/stdout. This resolves ROADMAP open
question #1 in favor of "no SDK": the repo stays dependency-free, and the
protocol surface used here (initialize, ping, tools, resources, prompts) is
small and stable.

The server is stateless: every tool call receives a temp_dir and reads/writes
the same files the CLI uses. Logs emitted by library code are captured inside
tools.py and never reach the protocol stream.
"""

import json
import sys
from pathlib import Path

from . import tools as tool_mod
from .paths import PathError, Workspace

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'translate-book-parallel-pro'
SERVER_VERSION = '1.3.0'

MAX_LINE_BYTES = 64 * 1024 * 1024  # a full book never crosses the wire; cap anyway


# ---------------------------------------------------------------------------
# static capability payloads
# ---------------------------------------------------------------------------

TOOL_DEFS = [
    {
        'name': 'convert_book',
        'description': (
            'Convert a PDF/DOCX/EPUB book into markdown chunks '
            '(scripts/convert.py). Returns the temp_dir, chunk_count and '
            'manifest source_hash.'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['input_file'],
            'properties': {
                'input_file': {'type': 'string', 'description': 'path inside the workspace'},
                'output_lang': {'type': 'string', 'description': 'target language code (default ru)'},
                'input_lang': {'type': 'string', 'description': 'source language (default auto)'},
                'chunk_size': {'type': 'integer', 'description': 'target chunk size in characters'},
                'temp_root': {'type': 'string', 'description': 'where to create {book}_temp (default workspace root)'},
            },
        },
    },
    {
        'name': 'get_status',
        'description': 'Snapshot of manifest, run_state progress and glossary for a temp dir.',
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {'temp_dir': {'type': 'string'}},
        },
    },
    {
        'name': 'get_translation_plan',
        'description': 'Which chunks need translation / recording / are unchanged.',
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'retranslate_untracked': {'type': 'boolean'},
            },
        },
    },
    {
        'name': 'get_chunk_prompt',
        'description': (
            'Full per-chunk translation prompt: task line, rules, term table '
            '(rule #13, omitted without glossary) and read-only neighbor '
            'context. The host translates it itself or hands it to sub-agents.'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir', 'chunk_id', 'target_language'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'chunk_id': {'type': 'string', 'description': 'chunk0001'},
                'target_language': {'type': 'string', 'description': 'e.g. Russian'},
                'top_n': {'type': 'integer'},
            },
        },
    },
    {
        'name': 'submit_translation',
        'description': (
            'Write output_chunkNNNN.md (and optional meta JSON) for a chunk; '
            'returns the validation result (UTF-8 text, non-empty, sha256).'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir', 'chunk_id', 'content'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'chunk_id': {'type': 'string'},
                'content': {'type': 'string', 'description': 'translated markdown text'},
                'meta': {'type': 'object', 'description': 'output_chunkNNNN.meta.json payload'},
            },
        },
    },
    {
        'name': 'merge_meta',
        'description': (
            'Prepare glossary merge decisions from worker meta files '
            '(merge_meta.py prepare-merge); apply=true passes a decisions '
            'object to apply-merge.'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'apply': {'type': 'boolean'},
                'decisions': {'type': 'object'},
            },
        },
    },
    {
        'name': 'validate_book',
        'description': 'Manifest/chunk-set validation gate before merging.',
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {'temp_dir': {'type': 'string'}},
        },
    },
    {
        'name': 'build_book',
        'description': (
            'Merge translated chunks and build DOCX/EPUB/PDF '
            '(scripts/merge_and_build.py). Returns output paths and sizes.'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'title': {'type': 'string'},
                'author': {'type': 'string'},
                'lang': {'type': 'string'},
            },
        },
    },
]

PROMPT_DEFS = [
    {
        'name': 'translate_chunk',
        'description': 'Inject a ready-to-use translation prompt for one chunk.',
        'arguments': [
            {'name': 'temp_dir', 'description': 'temp directory under the workspace', 'required': True},
            {'name': 'chunk_id', 'description': 'chunk0001', 'required': True},
            {'name': 'target_language', 'description': 'e.g. Russian', 'required': True},
        ],
    },
    {
        'name': 'review_translation',
        'description': 'Quality-check prompt comparing an output chunk with its source.',
        'arguments': [
            {'name': 'temp_dir', 'required': True},
            {'name': 'chunk_id', 'required': True},
            {'name': 'target_language', 'required': True},
        ],
    },
]

RESOURCE_KINDS = ('glossary', 'manifest')


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

def _tool_dispatch(ws, name, arguments):
    impls = {
        'convert_book': tool_mod.convert_book,
        'get_status': tool_mod.get_status,
        'get_translation_plan': tool_mod.get_translation_plan,
        'get_chunk_prompt': tool_mod.get_chunk_prompt,
        'submit_translation': tool_mod.submit_translation,
        'merge_meta': tool_mod.merge_meta,
        'validate_book': tool_mod.validate_book,
        'build_book': tool_mod.build_book,
    }
    impl = impls.get(name)
    if impl is None:
        raise KeyError(name)
    return impl(ws, arguments or {})


def _read_resource(ws, uri):
    import re
    chunk_id_re = re.compile(r'^chunk\d{4}$')
    prefix = 'translate-book://temp/'
    if not uri.startswith(prefix):
        raise KeyError(uri)
    parts = uri[len(prefix):].split('/')
    if len(parts) == 2 and parts[1] in RESOURCE_KINDS:
        temp_id, kind = parts
        temp_dir = ws.temp_dir(temp_id)
        path = Path(temp_dir) / f'{kind}.json'
    elif len(parts) == 3 and parts[1] in ('chunks', 'output'):
        # ROADMAP resource shape: .../chunks/{chunk_id} and .../output/{chunk_id}
        temp_id, kind, ref = parts
        temp_dir = ws.temp_dir(temp_id)
        if chunk_id_re.match(ref):
            name = ref if kind == 'chunks' else f'output_{ref}'
            name = f'{name}.md'
        else:
            name = ref
        path = ws.chunk_file(
            temp_dir, name, kind='source' if kind == 'chunks' else 'output',
        )
    else:
        raise KeyError(uri)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding='utf-8')


def _list_resources(ws):
    """Enumerate temp dirs under the workspace root; large content stays on disk."""
    items = []
    for temp_dir in sorted(ws.root.glob('*_temp')):
        if not temp_dir.is_dir():
            continue
        tid = temp_dir.name
        for kind in RESOURCE_KINDS:
            if (temp_dir / f'{kind}.json').is_file():
                items.append({
                    'uri': f'translate-book://temp/{tid}/{kind}',
                    'name': f'{tid}/{kind}',
                    'mimeType': 'application/json',
                })
    return items


def _get_prompt(ws, name, arguments):
    arguments = arguments or {}
    if name == 'translate_chunk':
        text = tool_mod.get_chunk_prompt(ws, arguments)['prompt']
    elif name == 'review_translation':
        temp_dir = str(ws.resolve_dir(arguments.get('temp_dir', '')))
        chunk_id = arguments.get('chunk_id', '')
        lang = arguments.get('target_language', 'ru')
        text = tool_mod.prompts.build_review_prompt(
            source_path=str(Path(temp_dir) / f'{chunk_id}.md'),
            output_path=str(Path(temp_dir) / f'output_{chunk_id}.md'),
            target_language=lang,
        )
    else:
        raise KeyError(name)
    return {
        'messages': [
            {'role': 'user', 'content': {'type': 'text', 'text': text}},
        ],
    }


def handle_message(state, msg):
    """Process one JSON-RPC message dict; returns a response dict or None
    for notifications/invalid-id requests."""
    method = msg.get('method')
    msg_id = msg.get('id')

    if msg_id is None:
        # JSON-RPC notification: never answered, whatever the method is.
        return None

    if method == 'initialize':
        return {
            'id': msg_id,
            'result': {
                'protocolVersion': msg.get('params', {}).get(
                    'protocolVersion', PROTOCOL_VERSION),
                'capabilities': {
                    'tools': {'listChanged': False},
                    'resources': {'subscribe': False, 'listChanged': False},
                    'prompts': {'listChanged': False},
                },
                'serverInfo': {'name': SERVER_NAME, 'version': SERVER_VERSION},
            },
        }

    if method == 'ping':
        return {'id': msg_id, 'result': {}}

    if method == 'tools/list':
        return {'id': msg_id, 'result': {'tools': TOOL_DEFS}}

    if method == 'tools/call':
        params = msg.get('params') or {}
        name = params.get('name', '')
        try:
            result = _tool_dispatch(state['workspace'], name, params.get('arguments'))
            return {
                'id': msg_id,
                'result': {
                    'content': [{'type': 'text',
                                 'text': json.dumps(result, ensure_ascii=False,
                                                    indent=2)}],
                    'isError': False,
                },
            }
        except KeyError:
            return _error(msg_id, -32602, f'Unknown tool: {name}')
        except (PathError, tool_mod.ToolError, FileNotFoundError, ValueError) as e:
            return _error(msg_id, -32000, f'{name} failed: {e}')

    if method == 'resources/list':
        return {'id': msg_id, 'result': {'resources': _list_resources(state['workspace'])}}

    if method == 'resources/read':
        uri = (msg.get('params') or {}).get('uri', '')
        try:
            text = _read_resource(state['workspace'], uri)
        except KeyError:
            return _error(msg_id, -32602, f'Unknown resource URI: {uri}')
        except PathError as e:
            return _error(msg_id, -32602, f'Invalid resource URI: {e}')
        except FileNotFoundError:
            return _error(msg_id, -32002, f'Resource not found: {uri}')
        return {
            'id': msg_id,
            'result': {'contents': [
                {'uri': uri, 'mimeType': 'text/plain; charset=utf-8', 'text': text},
            ]},
        }

    if method == 'prompts/list':
        return {'id': msg_id, 'result': {'prompts': PROMPT_DEFS}}

    if method == 'prompts/get':
        params = msg.get('params') or {}
        try:
            return {
                'id': msg_id,
                'result': _get_prompt(
                    state['workspace'], params.get('name', ''), params.get('arguments'),
                ),
            }
        except KeyError:
            return _error(msg_id, -32602, f'Unknown prompt: {params.get("name")}')
        except (PathError, tool_mod.ToolError, FileNotFoundError, ValueError) as e:
            return _error(msg_id, -32000, f'prompt failed: {e}')

    if msg_id is None:
        return None  # unreachable: notifications are filtered above
    return _error(msg_id, -32601, f'Method not found: {method}')


def _error(msg_id, code, message):
    # msg_id=None is valid here: JSON-RPC responses to requests whose id
    # could not be parsed carry `"id": null`.
    return {'id': msg_id, 'error': {'code': code, 'message': message}}


def serve(workspace_root, stdin=None, stdout=None):
    """Run the stdio loop until EOF. stdin/stdout are injectable for tests."""
    state = {'workspace': Workspace(workspace_root)}
    fin = stdin if stdin is not None else sys.stdin
    fout = stdout if stdout is not None else sys.stdout
    for line in fin:
        line = line.strip()
        if not line:
            continue
        if len(line) > MAX_LINE_BYTES:
            resp = _error(None, -32700, 'request too large')
        else:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                resp = _error(None, -32700, f'parse error: {e}')
            else:
                if not isinstance(msg, dict):
                    resp = _error(None, -32600, 'request must be an object')
                else:
                    try:
                        resp = handle_message(state, msg)
                    except Exception as e:  # never kill the loop on one bad call
                        resp = _error(msg.get('id'), -32603,
                                      f'internal error: {e}')
        if resp is not None:
            fout.write(json.dumps(resp, ensure_ascii=False) + '\n')
            fout.flush()
