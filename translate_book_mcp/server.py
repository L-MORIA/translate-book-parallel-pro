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
import os
import sys
import urllib.parse
from pathlib import Path

from . import tools as tool_mod
from .paths import PathError, Workspace

PROTOCOL_VERSION = '2024-11-05'
SERVER_NAME = 'translate-book-parallel-pro'
SERVER_VERSION = '1.3.4'

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
                'output_lang': {'type': 'string', 'description': 'target language code (default zh, same as convert.py)'},
                'input_lang': {'type': 'string', 'description': 'source language (default auto)'},
                'chunk_size': {'type': 'integer', 'description': 'target chunk size in characters'},
                'temp_root': {'type': 'string', 'description': 'where to create {book}_temp (default workspace root)'},
                'strip_page_numbers': {'type': 'boolean', 'description': 'pass --strip-page-numbers to convert.py'},
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
                'include_chunks': {'type': 'boolean', 'description': 'include the per-chunk detail array (default true)'},
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
            'required': ['temp_dir', 'chunk_id'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'chunk_id': {'type': 'string', 'description': 'chunk0001'},
                'target_language': {'type': 'string', 'description': 'e.g. Russian; defaults to config.txt output_lang'},
                'top_n': {'type': 'integer'},
                'custom_instructions': {'type': 'string', 'description': 'extra rule #12 for this chunk'},
                'include_source_text': {'type': 'boolean', 'description': 'include the chunk text in the result (default false)'},
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
            'required': ['temp_dir', 'chunk_id'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'chunk_id': {'type': 'string'},
                'content': {'type': 'string', 'description': 'translated markdown text; provide this or content_path'},
                'content_path': {'type': 'string', 'description': 'workspace file containing the translated markdown; provide this or content'},
                'meta': {'type': 'object', 'description': 'output_chunkNNNN.meta.json payload; synthesized empty when omitted'},
                'record': {'type': 'boolean', 'description': 'record the chunk in run_state.json (default true)'},
            },
        },
    },
    {
        'name': 'merge_meta',
        'description': (
            'Prepare, apply or inspect glossary merge decisions from worker '
            'meta files (merge_meta.py prepare-merge/apply-merge/status).'
        ),
        'inputSchema': {
            'type': 'object',
            'required': ['temp_dir'],
            'properties': {
                'temp_dir': {'type': 'string'},
                'action': {'type': 'string', 'enum': ['prepare', 'apply', 'status'], 'description': 'default prepare; apply requires decisions'},
                'apply': {'type': 'boolean', 'description': 'legacy shorthand for action=apply'},
                'decisions': {'type': 'object', 'description': 'full decisions document for action=apply'},
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
                'cover': {'type': 'string', 'description': 'workspace path to a cover image'},
                'export_name': {'type': 'string', 'description': 'filename stem for exported aliases'},
                'cleanup': {'type': 'boolean', 'description': 'remove rebuildable intermediates after a successful build'},
                'cleanup_translations': {'type': 'boolean', 'description': 'with cleanup, also delete chunk/output files'},
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
            {'name': 'target_language', 'description': 'e.g. Russian; defaults to config.txt output_lang', 'required': False},
        ],
    },
    {
        'name': 'review_translation',
        'description': 'Quality-check prompt comparing an output chunk with its source.',
        'arguments': [
            {'name': 'temp_dir', 'required': True},
            {'name': 'chunk_id', 'required': True},
            {'name': 'target_language', 'description': 'defaults to config.txt output_lang', 'required': False},
        ],
    },
]

RESOURCE_KINDS = ('glossary', 'manifest')

# Directories that never contain book temp dirs and can be huge; `tests/
# .artifacts` is deliberately not here — that is where test books live.
_WALK_SKIP = {
    '.git', '.hg', '.svn', '.idea', '.vscode', '.tox', '.venv', 'venv',
    'node_modules', '__pycache__', '.mypy_cache', '.pytest_cache',
    '.ruff_cache',
}

RESOURCE_TEMPLATES = [
    {
        'uriTemplate': 'translate-book://temp/{temp_path}/glossary',
        'name': 'Glossary',
        'description': (
            'Term glossary JSON for a temp book directory. {temp_path} is a '
            'workspace-relative path; slashes may be percent-encoded.'
        ),
        'mimeType': 'application/json',
    },
    {
        'uriTemplate': 'translate-book://temp/{temp_path}/manifest',
        'name': 'Manifest',
        'description': (
            'Chunk manifest JSON for a temp book directory. {temp_path} is a '
            'workspace-relative path; slashes may be percent-encoded.'
        ),
        'mimeType': 'application/json',
    },
    {
        'uriTemplate': 'translate-book://temp/{temp_path}/chunks/{chunk_id}',
        'name': 'Source chunk',
        'description': 'One source markdown chunk',
        'mimeType': 'text/markdown',
    },
    {
        'uriTemplate': 'translate-book://temp/{temp_path}/output/{chunk_id}',
        'name': 'Translated chunk',
        'description': 'One translated markdown chunk',
        'mimeType': 'text/markdown',
    },
]


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


def _decode_temp_parts(ws, parts):
    """Validate decoded URI path components and resolve the temp directory."""
    if not parts:
        raise KeyError('empty temp path')
    for part in parts:
        if part in ('', '.', '..') or '\\' in part or ':' in part or '\x00' in part:
            raise PathError(f'Invalid temp path component: {part!r}')
    temp_dir = ws.resolve_dir('/'.join(parts))
    if not temp_dir.name.endswith('_temp'):
        raise PathError(
            f"Resource temp directory must end with '_temp': {temp_dir.name}"
        )
    return temp_dir


def _read_resource(ws, uri):
    import re
    chunk_id_re = re.compile(r'^chunk\d{4}$')
    prefix = 'translate-book://temp/'
    if not uri.startswith(prefix):
        raise KeyError(uri)
    # Decoding the whole tail also accepts clients that percent-encode the
    # slashes of a nested temp path (RFC 6570 simple expansion).
    parts = urllib.parse.unquote(uri[len(prefix):]).split('/')
    if len(parts) >= 2 and parts[-1] in RESOURCE_KINDS:
        temp_parts, kind = parts[:-1], parts[-1]
        temp_dir = _decode_temp_parts(ws, temp_parts)
        path = Path(temp_dir) / f'{kind}.json'
        mime = 'application/json'
    elif len(parts) >= 3 and parts[-2] in ('chunks', 'output'):
        # ROADMAP resource shape: .../chunks/{chunk_id} and .../output/{chunk_id}
        temp_parts, kind, ref = parts[:-2], parts[-2], parts[-1]
        temp_dir = _decode_temp_parts(ws, temp_parts)
        if not chunk_id_re.match(ref):
            raise PathError(f'Expected chunk id like chunk0001, got {ref!r}')
        name = f'{ref}.md' if kind == 'chunks' else f'output_{ref}.md'
        path = ws.chunk_file(
            temp_dir, name, kind='source' if kind == 'chunks' else 'output',
        )
        mime = 'text/markdown; charset=utf-8'
    else:
        raise KeyError(uri)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding='utf-8'), mime


def _iter_temp_dirs(root):
    """Yield every `*_temp` directory under the workspace, nested included."""
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _WALK_SKIP)
        current = Path(dirpath)
        if current != root and current.name.endswith('_temp'):
            dirnames[:] = []  # a book temp dir can hold thousands of images
            yield current


def _list_resources(ws):
    """Enumerate temp dirs under the workspace root; large content stays on disk."""
    items = []
    for temp_dir in _iter_temp_dirs(ws.root):
        try:
            # Resolving rejects a `*_temp` symlink that points outside the root.
            temp_dir = ws.resolve_dir(str(temp_dir))
        except PathError:
            continue
        rel = temp_dir.relative_to(ws.root)
        temp_path = '/'.join(
            urllib.parse.quote(part, safe='') for part in rel.parts
        )
        for kind in RESOURCE_KINDS:
            if (temp_dir / f'{kind}.json').is_file():
                items.append({
                    'uri': f'translate-book://temp/{temp_path}/{kind}',
                    'name': f'{rel.as_posix()}/{kind}',
                    'mimeType': 'application/json',
                })
    return items


def _get_prompt(ws, name, arguments):
    arguments = arguments or {}
    if name == 'translate_chunk':
        text = tool_mod.get_chunk_prompt(ws, arguments)['prompt']
    elif name == 'review_translation':
        text = tool_mod.review_prompt(ws, arguments)['prompt']
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

    if method == 'resources/templates/list':
        return {'id': msg_id, 'result': {'resourceTemplates': RESOURCE_TEMPLATES}}

    if method == 'resources/read':
        uri = (msg.get('params') or {}).get('uri', '')
        try:
            text, mime = _read_resource(state['workspace'], uri)
        except KeyError:
            return _error(msg_id, -32602, f'Unknown resource URI: {uri}')
        except PathError as e:
            return _error(msg_id, -32602, f'Invalid resource URI: {e}')
        except FileNotFoundError:
            return _error(msg_id, -32002, f'Resource not found: {uri}')
        return {
            'id': msg_id,
            'result': {'contents': [
                {'uri': uri, 'mimeType': mime, 'text': text},
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
            # Every JSON-RPC response must carry the protocol marker. Strict
            # clients (OpenCode V2) reject messages without it even when the
            # payload is otherwise valid.
            resp.setdefault('jsonrpc', '2.0')
            fout.write(json.dumps(resp, ensure_ascii=False) + '\n')
            fout.flush()
