#!/usr/bin/env python
"""
merge_and_build.py - Merge translated pages and build final outputs
Combines original steps 4-7: merge -> HTML -> TOC -> DOCX/EPUB/PDF

Usage: merge_and_build.py --temp-dir <path> [--title <title>] [--author <author>] [--lang <lang>]

NOTE: This module is now a thin orchestrator. The pipeline logic lives in the
sibling _mab_* modules (decomposition; no behavior change). Names are re-exported
here so that:
  - tests that do `mock.patch.object(merge_and_build, "<name>", ...)` still patch
    the binding that main() resolves at call time;
  - tests that call `merge_and_build.<name>(...)` still find the function.
Do NOT remove the re-export block below without updating the test suite.
"""

import os
import sys
import glob
import argparse

# subprocess is a singleton in sys.modules: tests patch
# `merge_and_build.subprocess.run`, and generate_format() in _mab_formats sees
# the same patch because it imports the same `subprocess` module object.
import subprocess

# -----------------------------------------------------------------------------
# Re-export the decomposed subsystem so the merge_and_build namespace keeps the
# same public/patchable surface it had before the split.
# -----------------------------------------------------------------------------
from _mab_common import (
    SCRIPT_DIR,
    LANG_CONFIG,
    _DEFAULT_LANG_CONFIG,
    get_lang_config,
    load_config,
    natural_sort_key,
)
from _mab_images import (
    _validate_chunk_images,
    _check_generated_html_sanity,
)
from _mab_merge import merge_markdown_files
from _mab_html import (
    check_pandoc_available,
    convert_with_pandoc,
    convert_with_python_markdown,
    convert_with_basic_regex,
    apply_template_to_html,
    process_html_separators,
    convert_md_to_html,
    MARKDOWN_AVAILABLE,
)
from _mab_toc import (
    generate_heading_id,
    generate_simple_toc_html,
    insert_toc_with_bs4,
    insert_toc_with_regex,
    add_toc,
    BS4_AVAILABLE,
)
from _mab_formats import (
    generate_format,
    generate_formats,
    _validate_export_name,
    export_named_aliases,
)


# =============================================================================
# Intermediate-artifact cleanup (used only by main)
# =============================================================================

# Rebuildable from the source book (or from output.md) at any time.
REGENERABLE_INTERMEDIATES = ['input.html', 'input.md', 'output.html']
# chunk*.md are the source slices, output_chunk*.md are the translations.
# Deleting the translations means the book can only be rebuilt by translating
# it again, so that is opt-in.
CHUNK_PATTERNS = ['chunk*.md', 'output_chunk*.md']


def cleanup_intermediate_files(temp_dir, remove_chunks=False):
    """Remove intermediate artifacts, keeping the final outputs.

    By default the translation chunks survive: without output_chunk*.md the
    book cannot be rebuilt (new title, font, cover, export name) unless the
    whole book is translated from scratch. `remove_chunks=True` is the
    explicit "I am done with this temp dir" switch.
    """
    print("\n=== Cleaning up intermediate files ===")

    targets = [
        name for name in REGENERABLE_INTERMEDIATES
        if os.path.exists(os.path.join(temp_dir, name))
    ]
    chunk_paths = []
    if remove_chunks:
        for pattern in CHUNK_PATTERNS:
            chunk_paths.extend(sorted(glob.glob(os.path.join(temp_dir, pattern))))

    # Say what is about to go before touching it.
    if targets or chunk_paths:
        print(f"Removing {len(targets) + len(chunk_paths)} intermediate file(s):")
        for name in targets:
            print(f"  {name}")
        if chunk_paths:
            print(f"  {len(chunk_paths)} chunk files (chunk*.md, output_chunk*.md)")
    else:
        print("No intermediate files to remove.")

    for name in targets:
        os.remove(os.path.join(temp_dir, name))
    for path in chunk_paths:
        os.remove(path)

    if remove_chunks:
        print("Translations were deleted too - rebuilding this book requires translating it again.")
        return

    kept = 0
    for pattern in CHUNK_PATTERNS:
        kept += len(glob.glob(os.path.join(temp_dir, pattern)))
    if kept:
        print(f"Kept {kept} chunk file(s): the book can be rebuilt without translating again.")
        print("Pass --cleanup-translations to delete them as well.")


# =============================================================================
# Main
# =============================================================================

def _resolve_title(title_arg, config):
    """Pick the book title: explicit --title, then the metadata title that
    convert.py stored in config.txt, then the input file name.

    The launcher used to pass the file name as --title, which overwrote the
    real metadata title; that is why the metadata comes before the fallback.
    """
    if title_arg:
        return title_arg
    title = config.get('original_title')
    if title:
        return title
    input_file = config.get('input_file', '')
    if input_file:
        # config.txt was written on the translating machine; its stored path
        # may use the other platform's separator (CI runs the suite on Linux).
        # Normalise both separators before taking the stem.
        return os.path.splitext(os.path.basename(input_file.replace('\\', '/')))[0]
    return 'Translated Book'


def main():
    parser = argparse.ArgumentParser(description='Merge translated pages and build final outputs')
    parser.add_argument('--temp-dir', required=True, help='Temp directory path')
    parser.add_argument('--title', default=None, help='Translated book title (override config)')
    parser.add_argument('--author', default=None, help='Author name (override config)')
    parser.add_argument('--lang', default=None, help='Output language code (override config)')
    parser.add_argument('--cover', default=None, help='Cover image path for EPUB output')
    parser.add_argument('--export-name', default=None, help='Optional filename stem for exported alias copies')
    parser.add_argument('--cleanup', action='store_true', help='Remove rebuildable intermediates after a successful build (translation chunks are kept)')
    parser.add_argument('--cleanup-translations', action='store_true', help='With --cleanup, also delete chunk*.md and output_chunk*.md (a rebuild then needs retranslation)')

    args = parser.parse_args()
    temp_dir = args.temp_dir

    if args.cleanup_translations and not args.cleanup:
        parser.error("--cleanup-translations requires --cleanup")

    if not os.path.isdir(temp_dir):
        print(f"Error: Temp directory not found: {temp_dir}")
        sys.exit(1)

    cover = args.cover
    if cover:
        if not os.path.isfile(cover):
            print(f"Error: Cover image not found: {cover}")
            sys.exit(1)
        cover = os.path.abspath(cover)

    export_name = None
    if args.export_name:
        try:
            export_name = _validate_export_name(args.export_name)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Load config as base, CLI args override
    config = load_config(temp_dir)

    lang_code = args.lang or config.get('output_lang', 'zh')
    lang_cfg = get_lang_config(lang_code)

    # Title: explicit --title, then the book's own metadata title from
    # config.txt (written by convert.py), then the input file name. Never
    # overwrite a real metadata title with the file name.
    title = _resolve_title(args.title, config)
    author = args.author or config.get('creator', 'Unknown Author')

    print("=== Merge and Build ===")
    print(f"Temp directory: {temp_dir}")
    print(f"Title: {title}")
    print(f"Author: {author}")
    print(f"Language: {lang_code} (attr: {lang_cfg['lang_attr']})")

    # Step 4: Merge
    if not merge_markdown_files(temp_dir):
        sys.exit(1)

    # Step 5: Convert to HTML
    if not convert_md_to_html(temp_dir, title, lang_cfg, author):
        sys.exit(1)

    # Step 6: Add TOC
    add_toc(temp_dir)

    # Step 7: Generate formats
    all_formats_ok = generate_formats(temp_dir, lang_cfg['lang_attr'], cover=cover)

    if export_name:
        if all_formats_ok:
            aliases = export_named_aliases(temp_dir, export_name)
            if aliases:
                print("\nExport aliases:")
                for name in aliases:
                    print(f"  {name}")
        else:
            print("\nSkipping export aliases — some formats failed.")

    print("\n=== Build Complete ===")
    print(f"All outputs saved to: {temp_dir}")

    # List generated files
    for ext in ['book.html', 'book_doc.html', 'book.docx', 'book.epub', 'book.pdf']:
        filepath = os.path.join(temp_dir, ext)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  {ext}: {size:,} bytes")

    # Cleanup intermediate artifacts if requested (skip if any format failed)
    if args.cleanup:
        if all_formats_ok:
            cleanup_intermediate_files(temp_dir, remove_chunks=args.cleanup_translations)
        else:
            print("\nSkipping cleanup — some formats failed. Intermediate files kept for diagnosis/retry.")

    # A failed format must fail the build: launchers and CI key on the exit code.
    if not all_formats_ok:
        print("\nSome output formats failed to generate — see errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
