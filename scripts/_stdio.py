#!/usr/bin/env python
"""UTF-8 standard streams for command-line entry points.

Windows uses the ANSI/OEM code page (cp1251, cp866, ...) for redirected
stdout/stderr. Printing the glossary table header (原文 | 别名 | 译文) or a
translated title then raises UnicodeEncodeError, and captured output is not
valid UTF-8 for the orchestrating agent. Each CLI calls
``configure_utf8_stdio()`` before producing output so the pipeline behaves
the same on every platform and locale.
"""

import sys


def configure_utf8_stdio(include_stdin=False):
    """Reconfigure the standard streams to UTF-8 when possible.

    Streams without ``reconfigure`` (e.g. StringIO in tests) and streams that
    cannot be reconfigured (detached or already written to) are left as-is.
    """
    streams = [sys.stdout, sys.stderr]
    if include_stdin:
        streams.insert(0, sys.stdin)
    for stream in streams:
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding='utf-8')
        except (ValueError, OSError):
            pass
