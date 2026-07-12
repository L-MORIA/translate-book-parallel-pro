#!/usr/bin/env python
"""_mab_images.py — Image-structure validation for the merge & build pipeline.

Verifies that each translated output_chunk preserves the image references of its
source chunk, and sanity-checks generated HTML for malformed <img> tags.
Extracted verbatim from merge_and_build.py (no behavior change).
"""

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


# =============================================================================
# Image structure validation helpers
# =============================================================================

# Markdown image: `![alt](url)` or `![alt](url "title")`.
# - Negative lookbehind on `\` skips escaped `\![...]` (renders as literal text).
# - Closing `)` is required — a missing `)` means the image won't render, so
#   such a fragment must NOT count as a preserved image reference.
_MD_IMG_RE = re.compile(r'(?<!\\)!\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)')
_VALID_ATTR_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_:.\-]*$')


class _ImgTagCollector(HTMLParser):
    """Collects every <img> tag found in fed text. Uses stdlib HTMLParser, which
    correctly handles `>` inside quoted attribute values — unlike a plain
    `<img\\b[^>]*>` regex, which would truncate at the first `>`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.records = []  # list of (raw_tag_text, attrs_list)

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.records.append((self.get_starttag_text(), list(attrs)))

    handle_startendtag = handle_starttag


def _scan_img_tags(text):
    """Return (Counter of <img> srcs, list of (raw_tag, bad_attr_name) tuples).

    Feeds the entire text to HTMLParser rather than pre-extracting tags via regex,
    so quoted attribute values containing `>` are handled correctly."""
    src_counts = Counter()
    bad_attrs = []
    parser = _ImgTagCollector()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:
        bad_attrs.append(('<unparseable input>', f'<parser error: {e}>'))
        return src_counts, bad_attrs
    for raw_tag, attrs in parser.records:
        for name, _ in attrs:
            if not _VALID_ATTR_NAME_RE.match(name):
                bad_attrs.append((raw_tag, name))
        for name, val in attrs:
            if name == 'src' and val:
                src_counts[val] += 1
    return src_counts, bad_attrs


def _scan_image_refs(text):
    """Return (Counter html_srcs, Counter md_srcs, list bad_attrs)."""
    html_srcs, bad_attrs = _scan_img_tags(text)
    md_srcs = Counter(_MD_IMG_RE.findall(text))
    return html_srcs, md_srcs, bad_attrs


def _validate_chunk_images(temp_dir):
    """Verify each output_chunk*.md preserves the image structure of its chunk*.md.

    Bad-attribute detection uses a per-chunk DELTA: a malformed <img> attribute
    is flagged only if it appears in the output chunk but not in the source
    chunk. This avoids false positives on code blocks that legitimately contain
    deliberately-broken <img> examples — both chunks carry the same example, so
    the delta is empty.

    Returns False on any divergence; collects all errors and prints them
    together so an agent can fix many chunks in one pass.
    """
    temp_path = Path(temp_dir)
    errors = []
    for src_chunk in sorted(temp_path.glob('chunk*.md')):
        if src_chunk.name.startswith('output_'):
            continue
        out_chunk = temp_path / f'output_{src_chunk.name}'
        if not out_chunk.exists():
            continue  # missing-output is the manifest validator's job
        src_html, src_md, src_bad = _scan_image_refs(src_chunk.read_text(encoding='utf-8'))
        out_html, out_md, out_bad = _scan_image_refs(out_chunk.read_text(encoding='utf-8'))

        src_bad_counts = Counter(name for _, name in src_bad)
        out_bad_counts = Counter(name for _, name in out_bad)
        new_bad_counts = out_bad_counts - src_bad_counts
        if new_bad_counts:
            new_bad_examples = [
                (raw_tag, attr_name)
                for raw_tag, attr_name in out_bad
                if new_bad_counts.get(attr_name, 0) > 0
            ]
            for raw_tag, attr_name in new_bad_examples:
                errors.append(
                    f"ERROR: {out_chunk.name} introduced malformed <img> tag (not present in source)\n"
                    f"  tag: {raw_tag}\n"
                    f"  problem: attribute name '{attr_name}' is not a valid HTML identifier\n"
                    f"  likely cause: an unescaped quote inside alt=\"...\" or title=\"...\" closed the attribute early\n"
                    f"  fix: in {out_chunk.name}, replace the inner quote with a curly quote in the target language or with &quot; / &#39;\n"
                    f"  source chunk for reference: {src_chunk.name}"
                )

        if src_html != out_html or src_md != out_md:
            errors.append(
                f"ERROR: {out_chunk.name} image references diverge from {src_chunk.name}\n"
                f"  missing <img src> (count): {sorted((src_html - out_html).items()) or 'none'}\n"
                f"  extra   <img src> (count): {sorted((out_html - src_html).items()) or 'none'}\n"
                f"  missing ![](path) (count): {sorted((src_md - out_md).items()) or 'none'}\n"
                f"  extra   ![](path) (count): {sorted((out_md - src_md).items()) or 'none'}\n"
                f"  fix: restore the missing image refs in {out_chunk.name} from {src_chunk.name}"
            )

    if errors:
        print("\n=== Image validation failed ===")
        for e in errors:
            print(e)
            print()
        return False
    return True


def _check_generated_html_sanity(html_path):
    """Sanity-check generated HTML for malformed <img> tags. Returns False on problems.

    Note: we deliberately do NOT flag `&lt;img` in the rendered HTML — books that
    discuss HTML in prose or code blocks legitimately render escaped `<img>` text,
    and that's not a corruption signal. Real corruption produces a malformed
    actual `<img>` tag, which the attribute-name check catches."""
    try:
        text = Path(html_path).read_text(encoding='utf-8')
    except Exception as e:
        print(f"ERROR: cannot read {html_path}: {e}")
        return False

    _, bad_attrs = _scan_img_tags(text)
    if not bad_attrs:
        return True

    print(f"ERROR: image sanity check failed on {Path(html_path).name}")
    for raw_tag, attr_name in bad_attrs:
        print(f"  - malformed <img>: {raw_tag}")
        print(f"    bad attribute name: '{attr_name}'")
    print(
        "  fix: inspect output.md and the corresponding output_chunk*.md;\n"
        "       if alt text contains literal quotes, replace with curly quotes or HTML entity"
    )
    return False
