"""MCP tool implementations (ROADMAP.md P0, milestones M1-M3).

The server is stateless: every call receives a temp_dir and reads/writes the
same files the CLI uses, so CLI and MCP behavior stay identical. Tools never
call an LLM.

Library calls that `print()` (manifest errors, run_state summaries, ...) are
wrapped in a stdout/stderr capture so nothing can pollute the JSON-RPC
stream; captured output is returned alongside the structured result as
`logs`. External pipelines (convert, build) run through list-argv
subprocess calls with `sys.executable` — no shell strings, per ROADMAP.md.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_SCRIPTS = _REPO_ROOT / 'scripts'
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import chunk_context  # noqa: E402
import glossary  # noqa: E402
import manifest  # noqa: E402
import run_state  # noqa: E402

from . import prompts  # noqa: E402
from .paths import PathError, Workspace  # noqa: E402

CHUNK_ID_RE = re.compile(r'^chunk\d{4}$')

BOOK_FORMATS = ('book.html', 'book.docx', 'book.epub', 'book.pdf')


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


def _run_python(script, *argv, cwd=None):
    """Run a repo CLI with a list argv; returns (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(_SCRIPTS / script), *argv]
    proc = subprocess.run(
        cmd, cwd=str(cwd or _REPO_ROOT), capture_output=True,
        text=True, encoding='utf-8', errors='replace', shell=False,
        timeout=1800,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _load_manifest_or_none(temp_dir, logs):
    try:
        with _capture() as (out, err):
            loaded = manifest.load_manifest(temp_dir)
        logs.extend(_drain(out, err))
        return loaded
    except manifest.ManifestError as e:
        logs.append(f"manifest error: {e}")
        return None


def _glossary_terms(temp_dir, logs):
    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.exists(glossary_path):
        return None  # documented "no glossary" mode — not an error
    try:
        with _capture() as (out, err):
            data = glossary.load_glossary(glossary_path)
        logs.extend(_drain(out, err))
        return data
    except (glossary.GlossaryError if hasattr(glossary, 'GlossaryError') else ValueError) as e:
        logs.append(f"glossary error: {e}")
        return None


# ---------------------------------------------------------------------------
# M1 — read-only tools
# ---------------------------------------------------------------------------

def convert_book(ws, args):
    """PDF/DOCX/EPUB -> markdown chunks via scripts/convert.py."""
    input_file = args.get('input_file')
    if not input_file:
        raise ToolError("input_file is required")
    input_path = str(ws.resolve_dir(input_file))
    if not os.path.isfile(input_path):
        raise ToolError(f"input_file does not exist: {input_path}")

    temp_root = args.get('temp_root') or str(ws.root)
    resolved_root = ws.resolve_dir(temp_root)

    argv = ['convert.py', input_path,
            '-l', str(args.get('input_lang', 'auto')),
            '--olang', str(args.get('output_lang', 'ru')),
            '--temp-root', str(resolved_root)]
    chunk_size = args.get('chunk_size')
    if chunk_size:
        argv += ['--chunk-size', str(int(chunk_size))]

    code, out, err = _run_python(*argv, cwd=str(resolved_root))
    logs = [line for line in (out + err).splitlines() if line.strip()]
    if code != 0:
        raise ToolError(
            "convert.py failed (exit %d); see logs for the reason" % code
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
        raise ToolError("convert.py produced no *_temp directory")

    mf = _load_manifest_or_none(str(temp_dir), logs)
    result = {
        'temp_dir': str(temp_dir),
        'temp_id': temp_dir.name,
        'chunk_count': mf['chunk_count'] if mf else None,
        'source_hash': mf.get('source_hash') if mf else None,
        'logs': logs,
    }
    return result


def get_status(ws, args):
    """manifest + run_state + glossary snapshot for a temp dir."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    logs = []
    status = run_state.status(temp_dir) or {}
    with _capture() as (out, err):
        mf = _load_manifest_or_none(temp_dir, logs)
    status.setdefault('logs', [])
    status['logs'] = status.get('logs', []) + _drain(out, err) + logs

    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if os.path.exists(glossary_path):
        data = _glossary_terms(temp_dir, logs)
        status['glossary'] = {
            'present': True,
            'term_count': len(data.get('terms', [])) if data else None,
        }
    else:
        status['glossary'] = {'present': False, 'term_count': 0}

    if mf:
        status['chunk_count'] = mf.get('chunk_count')
        outputs = mf.get('chunks', [])
        present = sum(
            1 for c in outputs
            if os.path.isfile(os.path.join(temp_dir, c.get('output_file', '')))
        )
        status['outputs_present'] = present
    else:
        status['chunk_count'] = status.get('chunk_count')
    return status


def get_translation_plan(ws, args):
    """Which chunks need translation (run_state.plan semantics)."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    retranslate = bool(args.get('retranslate_untracked', False))
    with _capture() as (out, err):
        plan = run_state.plan(temp_dir, retranslate_untracked=retranslate)
    plan['logs'] = _drain(out, err)
    return plan


def get_chunk_prompt(ws, args):
    """Full translation prompt for one chunk: rules + term table + neighbors."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    chunk_id = args.get('chunk_id', '')
    if not CHUNK_ID_RE.match(chunk_id or ''):
        raise PathError(f"Expected chunk id like chunk0001, got {chunk_id!r}")
    target_language = args.get('target_language') or 'ru'

    chunk_name = f'{chunk_id}.md'
    source_path = ws.chunk_file(Path(temp_dir), chunk_name)
    if not source_path.is_file():
        raise ToolError(f"source chunk not found: {chunk_name}")
    output_path = ws.chunk_file(Path(temp_dir), f'output_{chunk_id}.md', kind='output')
    meta_path = ws.chunk_file(
        Path(temp_dir), f'output_{chunk_id}.meta.json', kind='meta')

    chunk_text = source_path.read_text(encoding='utf-8')
    logs = []

    term_table = ''
    data = _glossary_terms(temp_dir, logs)
    if data:
        top_n = args.get('top_n')
        with _capture() as (out, err):
            terms = glossary.select_terms_for_chunk(
                data, chunk_text,
                top_n=int(top_n) if top_n else None,
            )
            term_table = glossary.format_terms_for_prompt(terms)
        logs.extend(_drain(out, err))

    neighbor_block = ''
    try:
        with _capture() as (out, err):
            ctx = chunk_context.get_neighbor_context(temp_dir, chunk_name)
            neighbor_block = chunk_context.format_for_prompt(ctx)
        logs.extend(_drain(out, err))
    except FileNotFoundError as e:
        logs.append(f"neighbor context unavailable: {e}")

    prompt = prompts.build_chunk_prompt(
        source_path=str(source_path), output_path=str(output_path),
        meta_path=str(meta_path), target_language=target_language,
        term_table=term_table, neighbor_context=neighbor_block,
    )
    return {
        'prompt': prompt,
        'chunk_id': chunk_id,
        'source_path': str(source_path),
        'output_path': str(output_path),
        'meta_path': str(meta_path),
        'term_table_present': bool(term_table),
        'neighbor_context_present': bool(neighbor_block),
        'target_language': target_language,
        'logs': logs,
    }


# ---------------------------------------------------------------------------
# M2 — write path
# ---------------------------------------------------------------------------

def submit_translation(ws, args):
    """Write output_chunkNNNN.md (+ optional meta) and validate the result."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    chunk_id = args.get('chunk_id', '')
    if not CHUNK_ID_RE.match(chunk_id or ''):
        raise PathError(f"Expected chunk id like chunk0001, got {chunk_id!r}")
    content = args.get('content')
    if not isinstance(content, str) or not content.strip():
        raise ToolError("content must be a non-empty string")

    source_path = ws.chunk_file(Path(temp_dir), f'{chunk_id}.md')
    if not source_path.is_file():
        raise ToolError(f"source chunk not found: {chunk_id}.md")
    output_path = ws.chunk_file(Path(temp_dir), f'output_{chunk_id}.md', kind='output')

    warnings = []
    source_text = source_path.read_text(encoding='utf-8', errors='replace')
    if len(source_text) > 1000 and len(content.strip()) < len(source_text) * 0.2:
        warnings.append(
            "output is suspiciously short compared to the source "
            "(< 20% of source characters)"
        )

    # explicit open(): Path.write_text(newline=...) exists only since 3.10,
    # and the supported matrix starts at 3.9. LF endings keep translated
    # outputs byte-stable across Windows and Linux.
    with open(output_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)

    meta = args.get('meta')
    meta_path = None
    if meta is not None:
        if not isinstance(meta, dict):
            raise ToolError("meta must be a JSON object")
        if 'chunk_id' in meta:
            raise ToolError("meta must not contain a chunk_id field")
        meta_path = ws.chunk_file(
            Path(temp_dir), f'output_{chunk_id}.meta.json', kind='meta')
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )

    return {
        'chunk_id': chunk_id,
        'output_path': str(output_path),
        'meta_path': str(meta_path) if meta_path else None,
        'bytes': output_path.stat().st_size,
        'sha256': manifest.file_hash(str(output_path)),
        'warnings': warnings,
    }


def merge_meta(ws, args):
    """Prepare (and optionally apply) glossary merge decisions."""
    temp_dir_arg = args.get('temp_dir')
    temp_dir = str(ws.resolve_dir(temp_dir_arg))
    glossary_path = os.path.join(temp_dir, 'glossary.json')
    if not os.path.exists(glossary_path):
        return {
            'status': 'no_glossary',
            'auto_apply': [],
            'decisions_needed': [],
            'summary': 'no glossary.json in this temp dir — nothing to merge',
            'logs': [],
        }

    code, out, err = _run_python('merge_meta.py', 'prepare-merge', temp_dir)
    logs = [line for line in (out + err).splitlines() if line.strip()]
    if code != 0:
        raise ToolError(
            "merge_meta prepare-merge failed (exit %d); see logs" % code
        )
    proposal = json.loads(out)

    applied = False
    if args.get('apply'):
        decisions = args.get('decisions')
        if not isinstance(decisions, dict):
            raise ToolError(
                "apply=true requires a decisions object (take it from the "
                "prepare-merge proposal)"
            )
        payload = json.dumps(decisions, ensure_ascii=False)
        proc = subprocess.run(
            [sys.executable, str(_SCRIPTS / 'merge_meta.py'), 'apply-merge', temp_dir],
            input=payload, capture_output=True, text=True,
            encoding='utf-8', errors='replace', shell=False, timeout=300,
        )
        logs += [line for line in (proc.stdout + proc.stderr).splitlines() if line.strip()]
        if proc.returncode != 0:
            raise ToolError(
                "merge_meta apply-merge failed (exit %d); see logs" % proc.returncode
            )
        applied = True

    return {
        'status': 'ok',
        'auto_apply': proposal.get('auto_apply', []),
        'decisions_needed': proposal.get('decisions_needed', []),
        'applied': applied,
        'summary': proposal.get('summary', ''),
        'logs': logs,
    }


def validate_book(ws, args):
    """Manifest/chunk-set validation before merge (manifest.validate_for_merge)."""
    temp_dir = str(ws.resolve_dir(args.get('temp_dir')))
    with _capture() as (out, err):
        ok, ordered, warnings = manifest.validate_for_merge(temp_dir)
    logs = _drain(out, err)
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
        raise ToolError(f"temp_dir does not exist: {temp_dir}")

    argv = ['merge_and_build.py', '--temp-dir', temp_dir]
    for key, flag in (('title', '--title'), ('author', '--author'), ('lang', '--lang')):
        value = args.get(key)
        if value:
            argv += [flag, str(value)]

    temp_path = Path(temp_dir)
    code, out, err = _run_python(*argv, cwd=str(temp_path.parent))
    logs = [line for line in (out + err).splitlines() if line.strip()]
    if code != 0:
        raise ToolError(
            "merge_and_build.py failed (exit %d); see logs for the reason" % code
        )

    outputs = {}
    for name in BOOK_FORMATS:
        path = Path(temp_dir) / name
        if path.is_file():
            outputs[name] = {'path': str(path), 'bytes': path.stat().st_size}
    return {'temp_dir': temp_dir, 'outputs': outputs, 'logs': logs}
