"""MCP tool implementations (ROADMAP.md P0, milestones M1-M3).

The server is stateless: every call receives a temp_dir and reads/writes the
same files the CLI uses, so CLI and MCP behavior stay identical. Tools never
call an LLM.

Library calls that `print()` (manifest errors, run_state summaries, ...) are
wrapped in a stdout/stderr capture so nothing can pollute the JSON-RPC
stream; captured output is returned alongside the structured result as
`logs`. External pipelines (convert, build, merge_meta) run through list-argv
subprocess calls with `sys.executable` — no shell strings, per ROADMAP.md.

The hardening options ported from the early prototype are deliberate:
translation writes are atomic and size-limited, `content_path` avoids sending
large strings through JSON-RPC, missing meta files are synthesized as empty
observations, and successful writes are recorded in run_state so the next
translation plan does not report the same chunk as "record only".
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_SCRIPTS = _REPO_ROOT / 'scripts'
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import chunk_context  # noqa: E402
import glossary  # noqa: E402
import manifest  # noqa: E402
import meta as meta_mod  # noqa: E402
import run_state  # noqa: E402

from . import prompts  # noqa: E402
from .paths import PathError, Workspace  # noqa: E402

CHUNK_ID_RE = re.compile(r'^chunk\d{4}$')

BOOK_FORMATS = ('book.html', 'book.docx', 'book.epub', 'book.pdf')
ARTIFACT_FILES = ('output.md', 'book.html', 'book_doc.html') + BOOK_FORMATS

MAX_TRANSLATION_CHARS = 5_000_000
MAX_DECISIONS_BYTES = 10_000_000
EMPTY_META = {
    'schema_version': 1,
    'new_entities': [],
    'alias_hypotheses': [],
    'attribute_hypotheses': [],
    'used_term_sources': [],
    'conflicts': [],
}
_STATE_LOCK = threading.Lock()


class ToolError(RuntimeError):
    """A tool-level failure that should reach the client as a clean message."""


@contextlib.contextmanager
def _capture():
    """Capture stdout+stderr emitted by imported library code."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


def _drain(out, err):
    logs = [line for line in out.getvalue().splitlines() if line.strip()]
    logs += [line for line in err.getvalue().splitlines() if line.strip()]
    return logs


def _trim_logs(lines, limit=200):
    """Keep tool responses small enough for a JSON-RPC frame."""
    if len(lines) <= limit:
        return lines
    return lines[:limit] + [
        '... %d more log line(s) truncated' % (len(lines) - limit)
    ]


def _tail(text, limit=4000):
    text = (text or '').strip()
    if len(text) <= limit:
        return text
    return '...\n' + text[-limit:]


def _timeout(env_name, default):
    try:
        value = int(os.environ.get(env_name, ''))
    except ValueError:
        return default
    return value if value > 0 else default


def _run_python(script, *argv, cwd=None, input_text=None, timeout=None):
    """Run a repo CLI with a list argv; returns (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(_SCRIPTS / script), *argv]
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd or _REPO_ROOT), input=input_text,
            capture_output=True, text=True, encoding='utf-8',
            errors='replace', shell=False, env=env,
            timeout=timeout if timeout is not None else 1800,
        )
    except subprocess.TimeoutExpired as exc:
        raise ToolError(
            '%s timed out after %s seconds' % (script, exc.timeout)
        ) from exc
    except OSError as exc:
        raise ToolError('Could not start %s: %s' % (script, exc)) from exc
    return proc.returncode, proc.stdout, proc.stderr


def _parse_json_output(text, label):
    text = (text or '').strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        if start >= 0:
            try:
                return json.loads(text[start:])
            except json.JSONDecodeError:
                pass
        raise ToolError(
            '%s did not return valid JSON. Output: %s'
            % (label, _tail(text, 2000))
        )


def _load_manifest_or_none(temp_dir, logs):
    """Return (manifest, error). Missing manifest is not an error."""
    try:
        with _capture() as (out, err):
            loaded = manifest.load_manifest(temp_dir)
        logs.extend(_drain(out, err))
        return loaded, None
    except manifest.ManifestError as exc:
        logs.append('manifest error: %s' % exc)
        return None, str(exc)


def _glossary_terms(temp_dir, logs):
    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.exists(glossary_path):
        return None  # documented "no glossary" mode — not an error
    try:
        with _capture() as (out, err):
            data = glossary.load_glossary(glossary_path)
        logs.extend(_drain(out, err))
        return data
    except (OSError, ValueError) as exc:
        logs.append('glossary error: %s' % exc)
        return None


def _read_config(temp_dir):
    """Parse the small key=value config.txt written by convert.py."""
    path = os.path.join(temp_dir, 'config.txt')
    config = {}
    if not os.path.isfile(path):
        return config
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            for line in handle:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    config[key] = value
    except OSError:
        pass
    return config


def _atomic_write_text(path, text):
    directory = os.path.dirname(os.path.abspath(path)) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix='.mcp-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _file_list(temp_dir, names):
    return [
        {'file': name, 'bytes': os.path.getsize(os.path.join(temp_dir, name))}
        for name in names
        if os.path.isfile(os.path.join(temp_dir, name))
    ]


def _chunk_status(ws, temp_dir, manifest_data):
    """Count missing/empty/unreadable translated chunks."""
    chunks = []
    if manifest_data:
        raw_chunks = manifest_data.get('chunks', [])
        if isinstance(raw_chunks, list):
            chunks = [item for item in raw_chunks if isinstance(item, dict)]

    def _order(item):
        value = item.get('order', 0)
        return value if isinstance(value, int) else 0

    chunks = sorted(chunks, key=_order)

    missing = []
    empty = []
    unreadable = []
    for chunk in chunks:
        chunk_id = chunk.get('id', '?')
        try:
            output_path = ws.chunk_file(
                Path(temp_dir), chunk.get('output_file', ''), kind='output',
            )
        except (PathError, KeyError, TypeError):
            unreadable.append(chunk_id)
            continue
        if not output_path.is_file():
            missing.append(chunk_id)
            continue
        if output_path.stat().st_size == 0:
            empty.append(chunk_id)
            continue
        output_text = manifest.read_output_text(str(output_path))
        if output_text is None or not output_text.strip():
            empty.append(chunk_id)

    return {
        'total': len(chunks),
        'translated': len(chunks) - len(missing) - len(empty) - len(unreadable),
        'missing_output_chunk_ids': missing,
        'empty_output_chunk_ids': empty,
        'unreadable_output_chunk_ids': unreadable,
    }


def _glossary_summary(temp_dir, logs):
    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.exists(glossary_path):
        return {'present': False, 'term_count': 0, 'version': None,
                'hash': None}
    try:
        with _capture() as (out, err):
            data = glossary.load_glossary(glossary_path)
        logs.extend(_drain(out, err))
        return {
            'present': True,
            'term_count': len(data.get('terms', [])),
            'version': data.get('version'),
            'hash': glossary.glossary_hash(data),
        }
    except (OSError, ValueError) as exc:
        return {'present': True, 'term_count': 0, 'version': None,
                'hash': None, 'error': str(exc)}


def _merge_meta_status(temp_dir):
    """Run merge_meta.py status and parse its JSON snapshot."""
    code, out, err = _run_python(
        'merge_meta.py', 'status', temp_dir, timeout=120,
    )
    logs = _trim_logs(
        [line for line in (out + err).splitlines() if line.strip()]
    )
    if code != 0:
        raise ToolError(
            'merge_meta status failed (exit %d); see logs' % code
        )
    return _parse_json_output(out, 'merge_meta status'), logs


# ---------------------------------------------------------------------------
# M1 — read-only tools
# ---------------------------------------------------------------------------

def convert_book(ws, args):
    """PDF/DOCX/EPUB -> markdown chunks via scripts/convert.py."""
    input_file = args.get('input_file')
    if not input_file:
        raise ToolError('input_file is required')
    # Resolve first (outer-workspace paths must stay PathError), then report a
    # missing file as a normal tool error.
    input_path = ws.resolve_file(input_file, must_exist=False,
                                 label='input_file')
    if not input_path.is_file():
        raise ToolError('input_file not found: %s' % input_path)
    if input_path.suffix.lower() not in ('.pdf', '.docx', '.epub'):
        raise ToolError(
            'input_file must be a PDF, DOCX or EPUB file, got %s'
            % (input_path.suffix or 'no extension')
        )

    temp_root = args.get('temp_root') or str(ws.root)
    resolved_root = ws.resolve_dir(temp_root)
    if resolved_root.exists() and not resolved_root.is_dir():
        raise ToolError('temp_root is not a directory: %s' % resolved_root)
    resolved_root.mkdir(parents=True, exist_ok=True)

    output_lang = args.get('output_lang') or 'zh'
    input_lang = args.get('input_lang') or 'auto'

    chunk_size = args.get('chunk_size')
    if chunk_size is not None:
        if isinstance(chunk_size, bool):
            raise ToolError('chunk_size must be an integer')
        try:
            chunk_size = int(chunk_size)
        except (TypeError, ValueError):
            raise ToolError('chunk_size must be an integer') from None
        if chunk_size < 500 or chunk_size > 1_000_000:
            raise ToolError(
                'chunk_size must be between 500 and 1000000 characters'
            )

    argv = ['convert.py', str(input_path),
            '-l', str(input_lang),
            '--olang', str(output_lang),
            '--temp-root', str(resolved_root)]
    if chunk_size is not None:
        argv += ['--chunk-size', str(chunk_size)]
    if args.get('strip_page_numbers'):
        argv.append('--strip-page-numbers')

    code, out, err = _run_python(
        *argv, cwd=str(resolved_root),
        timeout=_timeout('TRANSLATE_BOOK_MCP_CONVERT_TIMEOUT', 30 * 60),
    )
    logs = _trim_logs(
        [line for line in (out + err).splitlines() if line.strip()]
    )
    if code != 0:
        raise ToolError(
            'convert.py failed (exit %d); see logs for the reason' % code
        )

    # convert.py announces the exact directory it created; trust that instead
    # of a newest-wins mtime guess, which is ambiguous when two runs land in
    # the same timer tick (observed on Windows).
    temp_dir = None
    match = re.search(r'^Temp directory: (.+)$', out, re.MULTILINE)
    if match:
        printed = Path(match.group(1).strip())
        if not printed.is_absolute():
            printed = Path(resolved_root) / printed
        try:
            temp_dir = ws.resolve_dir(str(printed))
        except PathError:
            temp_dir = None
    if temp_dir is None:
        # fallback: the newest *_temp directory under temp_root
        candidates = sorted(
            (p for p in Path(resolved_root).glob('*_temp') if p.is_dir()),
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if candidates:
            temp_dir = candidates[0]
    if temp_dir is None:
        raise ToolError('convert.py produced no *_temp directory')

    mf, manifest_error = _load_manifest_or_none(str(temp_dir), logs)
    config = _read_config(str(temp_dir))
    return {
        'temp_dir': str(temp_dir),
        'temp_id': temp_dir.name,
        'chunk_count': mf['chunk_count'] if mf else None,
        'chunk_ids': [c.get('id') for c in mf.get('chunks', [])] if mf else [],
        'source_hash': mf.get('source_hash') if mf else None,
        'output_lang': config.get('output_lang', output_lang),
        'manifest_error': manifest_error,
        'logs': logs,
    }


def get_status(ws, args):
    """Manifest + run_state + glossary snapshot for a temp dir."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    logs = []

    run_state_error = None
    try:
        with _capture() as (out, err):
            status = run_state.status(temp_dir) or {}
        logs.extend(_drain(out, err))
    except Exception as exc:  # corrupt run_state/glossary is reported, not fatal
        status = {}
        run_state_error = str(exc)
        logs.append('run_state error: %s' % exc)

    mf, manifest_error = _load_manifest_or_none(temp_dir, logs)
    chunk_info = _chunk_status(ws, temp_dir, mf)
    config = _read_config(temp_dir)

    status.setdefault('temp_dir', temp_dir)
    status.setdefault('source_chunks', chunk_info['total'])
    status.setdefault('chunk_count', chunk_info['total'])
    status['run_state_error'] = run_state_error
    manifest_path = os.path.join(temp_dir, 'manifest.json')
    status['manifest'] = {
        'exists': os.path.exists(manifest_path),
        'error': manifest_error,
        'chunk_count': chunk_info['total'],
    }
    status['entries_error'] = manifest_error
    status['chunks'] = chunk_info
    status['config'] = config
    status['outputs_present'] = (
        chunk_info['total'] - len(chunk_info['missing_output_chunk_ids'])
    )
    status['glossary'] = _glossary_summary(temp_dir, logs)
    status['outputs'] = _file_list(temp_dir, ARTIFACT_FILES)

    meta_status = None
    meta_error = None
    glossary_path = os.path.join(temp_dir, 'glossary.json')
    has_meta = any(Path(temp_dir).glob('output_chunk*.meta.json'))
    if os.path.exists(glossary_path) or has_meta:
        try:
            report, meta_logs = _merge_meta_status(temp_dir)
            meta_status = report
            logs.extend(meta_logs)
        except ToolError as exc:
            meta_error = str(exc)
    status['meta'] = {'error': meta_error, 'status': meta_status}
    existing_logs = _drain_logs(status.pop('logs', []))
    status['logs'] = _trim_logs(existing_logs + logs)
    return status


def _drain_logs(lines):
    """Normalise a pre-existing logs list (run_state.status may supply one)."""
    return [line for line in (lines or []) if str(line).strip()]


def get_translation_plan(ws, args):
    """Which chunks need translation (run_state.plan semantics)."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    retranslate = bool(args.get('retranslate_untracked', False))
    with _capture() as (out, err):
        plan = run_state.plan(temp_dir, retranslate_untracked=retranslate)
    logs = _trim_logs(_drain(out, err))
    plan = dict(plan)
    plan['temp_dir'] = temp_dir
    next_ids = (plan.get('translation_chunk_ids')
                or plan.get('record_only_chunk_ids') or [])
    plan['next_chunk_id'] = next_ids[0] if next_ids else None
    if args.get('include_chunks') is False:
        plan.pop('chunks', None)
    plan['logs'] = logs
    return plan


def get_chunk_prompt(ws, args):
    """Full translation prompt for one chunk: rules + term table + neighbors."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    chunk_id = args.get('chunk_id', '')
    if not CHUNK_ID_RE.match(chunk_id or ''):
        raise PathError(
            'Expected chunk id like chunk0001, got %r' % chunk_id
        )

    source_path = ws.chunk_file(Path(temp_dir), '%s.md' % chunk_id)
    if not source_path.is_file():
        raise ToolError('source chunk not found: %s.md' % chunk_id)
    output_path = ws.chunk_file(
        Path(temp_dir), 'output_%s.md' % chunk_id, kind='output',
    )
    meta_path = ws.chunk_file(
        Path(temp_dir), 'output_%s.meta.json' % chunk_id, kind='meta',
    )

    try:
        chunk_text = source_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        raise ToolError(
            'Cannot read source chunk %s: %s' % (source_path, exc)
        ) from exc

    config = _read_config(temp_dir)
    target_input = (
        args.get('target_language')
        or config.get('output_lang')
        or 'zh'
    )
    target_input = str(target_input).strip() or 'zh'
    target_language = prompts.language_name(target_input)
    logs = []

    term_table = ''
    selected_terms = []
    glossary_hash = ''
    data = _glossary_terms(temp_dir, logs)
    if data:
        top_n = args.get('top_n')
        if top_n in (None, ''):
            top_n = None
        else:
            try:
                top_n = int(top_n)
            except (TypeError, ValueError):
                raise ToolError('top_n must be an integer') from None
        with _capture() as (out, err):
            selected_terms = glossary.select_terms_for_chunk(
                data, chunk_text, top_n=top_n,
            )
            term_table = glossary.format_terms_for_prompt(selected_terms)
        logs.extend(_drain(out, err))
        glossary_hash = glossary.glossary_hash(data)

    neighbor_block = ''
    try:
        with _capture() as (out, err):
            ctx = chunk_context.get_neighbor_context(temp_dir, '%s.md' % chunk_id)
            neighbor_block = chunk_context.format_for_prompt(ctx)
        logs.extend(_drain(out, err))
    except (OSError, ValueError) as exc:
        logs.append('neighbor context unavailable: %s' % exc)

    prompt = prompts.build_chunk_prompt(
        source_path=str(source_path), output_path=str(output_path),
        meta_path=str(meta_path), target_language=target_language,
        term_table=term_table, neighbor_context=neighbor_block,
        custom_instructions=args.get('custom_instructions') or '',
    )
    result = {
        'prompt': prompt,
        'chunk_id': chunk_id,
        'source_path': str(source_path),
        'output_path': str(output_path),
        'meta_path': str(meta_path),
        'target_language': target_language,
        'target_language_input': target_input,
        'char_count': len(chunk_text),
        'source_sha256': manifest.file_hash(str(source_path)),
        'glossary_hash': glossary_hash,
        'selected_term_ids': [
            term.get('id', term.get('source')) for term in selected_terms
        ],
        'term_table_present': bool(term_table),
        'neighbor_context_present': bool(neighbor_block),
        'meta_schema': prompts.meta_schema_template(),
        'logs': _trim_logs(logs),
    }
    if args.get('include_source_text'):
        result['source_text'] = chunk_text
    return result


# ---------------------------------------------------------------------------
# M2 — write path
# ---------------------------------------------------------------------------

def submit_translation(ws, args):
    """Write output_chunkNNNN.md (+ optional meta) and validate the result."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    chunk_id = args.get('chunk_id', '')
    if not CHUNK_ID_RE.match(chunk_id or ''):
        raise PathError(
            'Expected chunk id like chunk0001, got %r' % chunk_id
        )

    source_path = ws.chunk_file(Path(temp_dir), '%s.md' % chunk_id)
    if not source_path.is_file():
        raise ToolError('source chunk not found: %s.md' % chunk_id)
    output_path = ws.chunk_file(
        Path(temp_dir), 'output_%s.md' % chunk_id, kind='output',
    )
    meta_path = ws.chunk_file(
        Path(temp_dir), 'output_%s.meta.json' % chunk_id, kind='meta',
    )

    content = args.get('content')
    content_path = args.get('content_path')
    if (content is None) == (content_path is None):
        raise ToolError('Provide exactly one of content or content_path')

    if content_path is not None:
        source_of_content = ws.resolve_file(
            content_path, must_exist=True, label='content_path',
        )
        if os.path.normcase(str(source_of_content)) == os.path.normcase(
                str(source_path)):
            raise ToolError('content_path must not point at the source chunk')
        try:
            content = source_of_content.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(
                'Cannot read content_path %s: %s'
                % (source_of_content, exc)
            ) from exc

    if not isinstance(content, str):
        raise ToolError('content must be a string')
    if '\x00' in content:
        raise ToolError('content contains a NUL byte')
    if not content.strip():
        raise ToolError('Refusing to write an empty or whitespace-only translation')
    if len(content) > MAX_TRANSLATION_CHARS:
        raise ToolError(
            'Translation is too large (%d characters; max %d)'
            % (len(content), MAX_TRANSLATION_CHARS)
        )

    warnings = []
    try:
        source_text = source_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        source_text = ''
    if len(source_text) > 1000 and len(content.strip()) < len(source_text) * 0.2:
        warnings.append(
            'output is suspiciously short compared to the source '
            '(< 20% of source characters)'
        )

    meta_arg = args.get('meta')
    meta_payload = None
    meta_synthetic = False
    if meta_arg is not None:
        if not isinstance(meta_arg, dict):
            raise ToolError('meta must be a JSON object')
        try:
            meta_mod.validate_meta(meta_arg, str(meta_path))
        except ValueError as exc:
            raise ToolError('Invalid meta: %s' % exc) from exc
        meta_payload = meta_arg
    elif not meta_path.exists():
        meta_payload = dict(EMPTY_META)
        meta_synthetic = True

    recorded = False
    record_error = None
    record_logs = []
    with _STATE_LOCK:
        try:
            _atomic_write_text(str(output_path), content)
        except OSError as exc:
            raise ToolError(
                'Cannot write output chunk %s: %s' % (output_path, exc)
            ) from exc
        if meta_payload is not None:
            try:
                meta_mod.save_meta(str(meta_path), meta_payload)
            except ValueError as exc:
                raise ToolError('Invalid meta: %s' % exc) from exc
            except OSError as exc:
                raise ToolError(
                    'Cannot write meta file %s: %s' % (meta_path, exc)
                ) from exc
        if args.get('record', True):
            try:
                with _capture() as (out, err):
                    run_state.record_chunks(temp_dir, [chunk_id])
                record_logs = _drain(out, err)
                recorded = True
            except Exception as exc:  # output is written; report without losing it
                record_error = str(exc)

    return {
        'chunk_id': chunk_id,
        'output_file': output_path.name,
        'output_path': str(output_path),
        'bytes': output_path.stat().st_size,
        'sha256': manifest.file_hash(str(output_path)),
        'meta_file': meta_path.name,
        'meta_path': str(meta_path),
        'meta_written': meta_payload is not None,
        'meta_synthetic': meta_synthetic,
        'recorded': recorded,
        'record_error': record_error,
        'warnings': warnings,
        'logs': _trim_logs(record_logs),
    }


def merge_meta(ws, args):
    """Prepare, apply or inspect the glossary meta merge."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    action = (args.get('action') or '').strip().lower()
    if not action:
        action = 'apply' if args.get('apply') else 'prepare'
    if action not in ('prepare', 'apply', 'status'):
        raise ToolError("action must be one of: prepare, apply, status")

    if action == 'status':
        report, logs = _merge_meta_status(temp_dir)
        return {
            'status': 'ok',
            'action': 'status',
            'report': report,
            'logs': logs,
        }

    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.exists(glossary_path):
        return {
            'status': 'no_glossary',
            'action': action,
            'auto_apply': [],
            'decisions_needed': [],
            'applied': False,
            'summary': 'no glossary.json in this temp dir — nothing to merge',
            'logs': [],
        }

    if action == 'prepare':
        code, out, err = _run_python(
            'merge_meta.py', 'prepare-merge', temp_dir, timeout=300,
        )
        logs = _trim_logs(
            [line for line in (out + err).splitlines() if line.strip()]
        )
        if code != 0:
            raise ToolError(
                'merge_meta prepare-merge failed (exit %d); see logs' % code
            )
        proposal = _parse_json_output(out, 'merge_meta prepare-merge')
        return {
            'status': 'ok',
            'action': 'prepare',
            'auto_apply': proposal.get('auto_apply', []),
            'decisions_needed': proposal.get('decisions_needed', []),
            'applied': False,
            'summary': proposal.get('summary', ''),
            'logs': logs,
        }

    decisions = args.get('decisions')
    if not isinstance(decisions, dict):
        raise ToolError(
            'decisions must be a JSON object for action=apply '
            '(take it from the prepare-merge proposal)'
        )
    payload = json.dumps(decisions, ensure_ascii=False)
    if len(payload.encode('utf-8')) > MAX_DECISIONS_BYTES:
        raise ToolError('decisions payload is too large')
    with _STATE_LOCK:
        code, out, err = _run_python(
            'merge_meta.py', 'apply-merge', temp_dir,
            input_text=payload, timeout=300,
        )
    logs = _trim_logs(
        [line for line in (out + err).splitlines() if line.strip()]
    )
    if code != 0:
        raise ToolError(
            'merge_meta apply-merge failed (exit %d); see logs' % code
        )
    report = {}
    if (out or '').strip():
        try:
            report = _parse_json_output(out, 'merge_meta apply-merge')
        except ToolError:
            report = {}
    return {
        'status': 'ok',
        'action': 'apply',
        'applied': True,
        'report': report,
        'logs': logs,
    }


def validate_book(ws, args):
    """Manifest/chunk-set validation before merge (manifest.validate_for_merge)."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    with _capture() as (out, err):
        ok, ordered, warnings = manifest.validate_for_merge(temp_dir)
    logs = _trim_logs(_drain(out, err))
    return {
        'ok': bool(ok),
        'output_files': ordered,
        'warnings': warnings,
        'logs': logs,
    }


# ---------------------------------------------------------------------------
# M3 — build
# ---------------------------------------------------------------------------

def build_book(ws, args):
    """merge -> HTML -> DOCX/EPUB/PDF via scripts/merge_and_build.py."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    if not os.path.isdir(temp_dir):
        raise ToolError('temp_dir does not exist: %s' % temp_dir)

    cleanup = bool(args.get('cleanup'))
    cleanup_translations = bool(args.get('cleanup_translations'))
    if cleanup_translations and not cleanup:
        raise ToolError('cleanup_translations requires cleanup=True')

    argv = ['merge_and_build.py', '--temp-dir', temp_dir]
    for key, flag in (('title', '--title'), ('author', '--author'),
                      ('lang', '--lang')):
        value = args.get(key)
        if value:
            argv += [flag, str(value)]

    cover = args.get('cover')
    if cover:
        cover_path = ws.resolve_file(cover, must_exist=True, label='cover')
        argv += ['--cover', str(cover_path)]
    export_name = args.get('export_name')
    if export_name:
        argv += ['--export-name', str(export_name)]
    if cleanup:
        argv.append('--cleanup')
    if cleanup_translations:
        argv.append('--cleanup-translations')

    code, out, err = _run_python(
        *argv, cwd=str(Path(temp_dir).parent),
        timeout=_timeout('TRANSLATE_BOOK_MCP_BUILD_TIMEOUT', 60 * 60),
    )
    logs = _trim_logs(
        [line for line in (out + err).splitlines() if line.strip()]
    )
    if code != 0:
        raise ToolError(
            'merge_and_build.py failed (exit %d); see logs for the reason'
            % code
        )

    outputs = {
        name: {'path': str(Path(temp_dir) / name),
               'bytes': (Path(temp_dir) / name).stat().st_size}
        for name in BOOK_FORMATS
        if (Path(temp_dir) / name).is_file()
    }
    return {
        'temp_dir': temp_dir,
        'outputs': outputs,
        'artifacts': _file_list(temp_dir, ARTIFACT_FILES),
        'logs': logs,
    }


def review_prompt(ws, args):
    """Return a read-only quality-check prompt for one translated chunk."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    chunk_id = args.get('chunk_id', '')
    if not CHUNK_ID_RE.match(chunk_id or ''):
        raise PathError(
            'Expected chunk id like chunk0001, got %r' % chunk_id
        )
    config = _read_config(temp_dir)
    target_input = (
        args.get('target_language')
        or config.get('output_lang')
        or 'zh'
    )
    target_input = str(target_input).strip() or 'zh'
    source_path = ws.chunk_file(Path(temp_dir), '%s.md' % chunk_id)
    output_path = ws.chunk_file(
        Path(temp_dir), 'output_%s.md' % chunk_id, kind='output',
    )
    return {
        'prompt': prompts.build_review_prompt(
            source_path=str(source_path), output_path=str(output_path),
            target_language=target_input,
        ),
        'target_language': prompts.language_name(target_input),
        'target_language_input': target_input,
        'source_path': str(source_path),
        'output_path': str(output_path),
    }
