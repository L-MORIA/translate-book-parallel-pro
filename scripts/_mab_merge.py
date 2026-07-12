#!/usr/bin/env python
"""_mab_merge.py — Merge translated markdown chunks into output.md.

Extracted verbatim from merge_and_build.py (no behavior change). Depends on the
manifest module for hash validation and the sibling _mab_common/_mab_images
modules for natural ordering and image-structure checks.
"""

import os
import sys
import glob

from manifest import read_output_text, validate_for_merge
from _mab_common import natural_sort_key
from _mab_images import _validate_chunk_images


# =============================================================================
# Step 4: Merge translated markdown files
# =============================================================================

def merge_markdown_files(temp_dir):
    """Merge all translated output files into output.md"""
    print("=== Merging translated markdown files ===")

    output_md = os.path.join(temp_dir, 'output.md')

    # Always validate manifest, even if output.md exists (catch stale/corrupt outputs)
    ok, ordered_files, warnings = validate_for_merge(temp_dir)

    # Image structure validation runs unconditionally — bad chunks invalidate any cached output.md
    if not _validate_chunk_images(temp_dir):
        if os.path.exists(output_md):
            print("Removing stale output.md (built from chunks that failed image validation)")
            os.remove(output_md)
        return False

    if os.path.exists(output_md):
        if not ok:
            print("WARNING: output.md exists but manifest validation failed — deleting stale output.md")
            os.remove(output_md)
        else:
            # Check if any output_chunk is newer than output.md (re-translated chunks)
            output_md_mtime = os.path.getmtime(output_md)
            newer_chunks = []
            if ordered_files:
                newer_chunks = [
                    os.path.basename(f) for f in ordered_files
                    if os.path.getmtime(f) > output_md_mtime
                ]
            if newer_chunks:
                print(f"Re-merging — {len(newer_chunks)} chunk(s) newer than output.md: {', '.join(newer_chunks[:5])}{'...' if len(newer_chunks) > 5 else ''}")
                os.remove(output_md)
            else:
                print("Skipping merge - output.md already exists and is up to date")
                return True

    if not ok:
        print("ERROR: Merge validation failed. Fix the issues above before merging.")
        return False

    if ordered_files is not None:
        # Manifest-based merge
        print(f"Merging {len(ordered_files)} translated files (manifest-ordered)")
        merged_content = ""
        for file_path in ordered_files:
            content = read_output_text(file_path)
            if content is None:
                print(f"ERROR: Cannot read {os.path.basename(file_path)} — aborting merge")
                return False
            content = content.strip()
            if not content:
                # validate_for_merge already rejects blank outputs; this is a
                # last line of defense so a chunk can never vanish silently.
                print(f"ERROR: Blank output {os.path.basename(file_path)} — aborting merge")
                return False
            merged_content += content + "\n\n"
    else:
        # Legacy fallback: glob-based merge (no manifest)
        print("WARNING: No manifest.json found — using legacy glob-based merge.")
        print("  For hash validation, re-run convert.py to generate manifest.json")

        # Match chunk output files
        output_files = glob.glob(os.path.join(temp_dir, 'output_chunk*.md'))

        # Count original source files
        original_files = glob.glob(os.path.join(temp_dir, 'chunk*.md'))
        original_files = [f for f in original_files if not os.path.basename(f).startswith('output_')]

        if not output_files:
            print("Error: No translated markdown files found.")
            return False

        # Build expected output filename for each source file and verify 1:1 match
        source_basenames = sorted(
            [os.path.basename(f) for f in original_files],
            key=natural_sort_key
        )
        expected_outputs = set(f"output_{name}" for name in source_basenames)
        actual_outputs = set(os.path.basename(f) for f in output_files)

        missing = expected_outputs - actual_outputs
        orphaned = actual_outputs - expected_outputs

        if missing or orphaned:
            if missing:
                print(f"ERROR: Missing translations for: {', '.join(sorted(missing, key=natural_sort_key))}")
            if orphaned:
                print(f"ERROR: Orphaned outputs (no matching source): {', '.join(sorted(orphaned, key=natural_sort_key))}")
            return False

        # Verify no empty, unreadable, or whitespace-only output files
        for fp in output_files:
            if os.path.getsize(fp) == 0:
                print(f"ERROR: Empty output file: {os.path.basename(fp)}")
                return False
            text = read_output_text(fp)
            if text is None:
                print(f"ERROR: Unreadable output file: {os.path.basename(fp)}")
                return False
            if not text.strip():
                print(f"ERROR: Blank output file: {os.path.basename(fp)}")
                return False

        # Use source order to determine merge order (via expected output names)
        output_files = [
            os.path.join(temp_dir, f"output_{name}")
            for name in source_basenames
        ]
        print(f"Merging {len(output_files)} translated files (legacy glob)")

        merged_content = ""
        for file_path in output_files:
            content = read_output_text(file_path)
            if content is None:
                print(f"ERROR: Cannot read {os.path.basename(file_path)} — aborting merge")
                return False
            content = content.strip()
            if not content:
                print(f"ERROR: Blank output {os.path.basename(file_path)} — aborting merge")
                return False
            merged_content += content + "\n\n"

    try:
        with open(output_md, 'w', encoding='utf-8') as f:
            f.write(merged_content)
        file_size = os.path.getsize(output_md)
        print(f"Merged into output.md ({file_size:,} bytes)")
        return True
    except Exception as e:
        print(f"Error saving merged file: {e}")
        return False
