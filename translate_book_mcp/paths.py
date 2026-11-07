"""Workspace confinement and path validation for the MCP server.

Every tool call receives paths from a remote-capable client, so all of them
pass through here before touching the filesystem. The rules follow ROADMAP.md
§"Transport and security":

- everything must live inside the configured workspace root;
- `..` components, absolute paths outside the root and symlink escapes are
  rejected;
- chunk/output names must be exact `chunkNNNN.md` / `output_chunkNNNN.md` —
  no separators, no globs, no unicode tricks;
- temp IDs are a single path component.
"""

import os
import re
from pathlib import Path

CHUNK_NAME_RE = re.compile(r'^chunk\d{4}\.md$')
OUTPUT_NAME_RE = re.compile(r'^output_chunk\d{4}\.md$')
META_NAME_RE = re.compile(r'^output_chunk\d{4}\.meta\.json$')
CHUNK_ID_RE = re.compile(r'^chunk\d{4}$')

_FILE_KINDS = {
    'source': CHUNK_NAME_RE,
    'output': OUTPUT_NAME_RE,
    'meta': META_NAME_RE,
}


class PathError(ValueError):
    """Raised when a client-supplied path escapes the workspace or is malformed."""


class Workspace:
    """A resolved root directory; all tool paths must resolve inside it."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise PathError(f"Workspace root is not a directory: {root}")

    def _require_inside(self, resolved):
        try:
            resolved.relative_to(self.root)
        except ValueError:
            raise PathError(
                f"Path escapes the workspace root {self.root}: {resolved}"
            ) from None
        return resolved

    def resolve_dir(self, rel_dir):
        """Resolve a temp directory (relative to the root or absolute inside it)."""
        if not rel_dir or not str(rel_dir).strip():
            raise PathError("temp_dir must be a non-empty path")
        candidate = Path(rel_dir)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.root / candidate).resolve()
        return self._require_inside(resolved)

    def temp_dir(self, temp_id):
        """Resolve a bare temp directory NAME (single component, e.g.
        `sleepy-hollow_temp`) under the workspace root."""
        if not temp_id or os.path.basename(temp_id) != temp_id or temp_id in ('.', '..'):
            raise PathError(f"Invalid temp id: {temp_id!r}")
        if Path(temp_id).is_absolute() or '\\' in temp_id or '/' in temp_id:
            raise PathError(f"Invalid temp id: {temp_id!r}")
        resolved = (self.root / temp_id).resolve()
        return self._require_inside(resolved)

    def chunk_file(self, temp_dir, name, kind='source'):
        """Resolve `chunkNNNN.md` / `output_chunkNNNN.md` /
        `output_chunkNNNN.meta.json` inside a temp dir."""
        pattern = _FILE_KINDS[kind]
        if not name or not pattern.match(os.path.basename(name)) \
                or os.path.basename(name) != name:
            kind_names = {
                'source': 'chunkNNNN.md',
                'output': 'output_chunkNNNN.md',
                'meta': 'output_chunkNNNN.meta.json',
            }
            raise PathError(
                f"Expected filename like {kind_names[kind]}, got {name!r}"
            )
        resolved = (temp_dir / name).resolve()
        return self._require_inside(resolved)

    def chunk_id_dir(self, temp_dir, chunk_id):
        """Validate a bare chunk id (`chunk0001`) and return its temp dir."""
        if not chunk_id or not CHUNK_ID_RE.match(chunk_id):
            raise PathError(f"Expected chunk id like chunk0001, got {chunk_id!r}")
        return temp_dir


def resolve_workspace(root):
    """Build a Workspace, converting plain errors into PathError."""
    try:
        return Workspace(root)
    except PathError:
        raise
    except OSError as e:
        raise PathError(f"Cannot open workspace root {root!r}: {e}") from None
