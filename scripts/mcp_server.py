#!/usr/bin/env python
"""Thin stdio entry point for the translate-book MCP server.

Usage:
    python scripts/mcp_server.py [--workspace ROOT]

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio
transport) and confines every path to --workspace (default: the current
directory). Point any MCP-capable agent at this command; see ROADMAP.md and
AGENT_ADAPTER.md.
"""

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from _stdio import configure_utf8_stdio  # noqa: E402

from translate_book_mcp.server import SERVER_NAME, SERVER_VERSION, serve  # noqa: E402


def main():
    # stdin matters as much as stdout here: Windows pipes default to the ANSI
    # code page (cp1251 + surrogateescape), which corrupts UTF-8 JSON-RPC
    # payloads such as Russian translations.
    configure_utf8_stdio(include_stdin=True, errors='strict')
    parser = argparse.ArgumentParser(
        description=f'{SERVER_NAME} MCP server (stdio, JSON-RPC 2.0)',
    )
    parser.add_argument(
        '--workspace', default='.',
        help='root directory all tool paths are confined to (default: cwd)',
    )
    parser.add_argument('--version', action='version',
                        version=f'{SERVER_NAME} {SERVER_VERSION}')
    args = parser.parse_args()

    sys.stderr.write(
        f'{SERVER_NAME} {SERVER_VERSION} serving stdio; workspace={Path(args.workspace).resolve()}\n'
    )
    serve(args.workspace)


if __name__ == '__main__':
    main()
