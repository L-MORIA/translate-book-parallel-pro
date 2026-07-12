#!/usr/bin/env python
"""_mab_formats.py — Generate DOCX/EPUB/PDF outputs and optional export aliases.

Drives calibre_html_publish.py as a subprocess and produces the canonical
book.{docx,epub,pdf} artifacts plus optional user-facing filename copies.
Extracted verbatim from merge_and_build.py (no behavior change).
"""

import os
import sys
import glob
import shutil
import subprocess

from _mab_common import SCRIPT_DIR


# =============================================================================
# Step 7: Generate DOCX/EPUB/PDF with error transparency
# =============================================================================

def generate_format(html_file, temp_dir, output_ext, lang_attr, cover=None):
    """Generate a specific format using calibre_html_publish.py"""
    output_file = os.path.join(temp_dir, f"book{output_ext}")
    cover = cover if output_ext == '.epub' else None
    if cover and not os.path.isfile(cover):
        print(f"Cover image not found: {cover}")
        return None

    if os.path.exists(output_file):
        output_mtime = os.path.getmtime(output_file)

        # Check if source HTML is newer
        html_newer = os.path.getmtime(html_file) > output_mtime

        # Check if any image asset is newer (Calibre embeds these)
        images_newer = False
        images_dir = os.path.join(temp_dir, 'images')
        if os.path.isdir(images_dir):
            for img in os.listdir(images_dir):
                img_path = os.path.join(images_dir, img)
                if os.path.isfile(img_path) and os.path.getmtime(img_path) > output_mtime:
                    images_newer = True
                    break

        cover_newer = bool(cover and os.path.getmtime(cover) > output_mtime)

        if not html_newer and not images_newer and not cover_newer:
            file_size = os.path.getsize(output_file)
            print(f"Skipping {output_ext} - already exists and up to date ({file_size:,} bytes)")
            return output_file
        else:
            reasons = []
            if html_newer:
                reasons.append("source HTML changed")
            if images_newer:
                reasons.append("image assets changed")
            if cover_newer:
                reasons.append("cover image changed")
            print(f"Rebuilding {output_ext} - {', '.join(reasons)}")

    publish_script = os.path.join(SCRIPT_DIR, "calibre_html_publish.py")
    if not os.path.exists(publish_script):
        print(f"calibre_html_publish.py not found at: {publish_script}")
        return None

    try:
        cmd = [sys.executable, publish_script, html_file, "-o", output_file, "--lang", lang_attr]
        if cover:
            cmd.extend(["--cover", cover])
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)

        if os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            return output_file
        else:
            print(f"Failed to generate {output_ext}")
            if result.stdout:
                print(f"  stdout: {result.stdout[-500:]}")
            return None
    except subprocess.CalledProcessError as e:
        print(f"Failed to generate {output_ext}")
        if e.stdout:
            print(f"  stdout: {e.stdout[-500:]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[-500:]}")
        return None
    except Exception as e:
        print(f"Error generating {output_ext}: {e}")
        return None


def generate_formats(temp_dir, lang_attr, cover=None):
    """Generate DOCX, EPUB, and PDF with result summary"""
    print("=== Generating output formats ===")

    html_file = os.path.join(temp_dir, "book_doc.html")
    if not os.path.exists(html_file):
        html_files = glob.glob(os.path.join(temp_dir, "*.html"))
        if html_files:
            html_file = max(html_files, key=os.path.getmtime)
        else:
            print("No HTML files found for format generation")
            return

    results = {}
    for ext in ['.docx', '.epub', '.pdf']:
        result = generate_format(html_file, temp_dir, ext, lang_attr, cover=cover)
        if result:
            file_size = os.path.getsize(result)
            results[ext] = ('OK', f"{file_size:,} bytes")
        else:
            results[ext] = ('FAILED', '')

    # Print summary table
    print("\nFormat results:")
    has_failures = False
    for ext, (status, detail) in results.items():
        if status == 'OK':
            print(f"  {ext}: {status} ({detail})")
        else:
            print(f"  {ext}: {status}")
            has_failures = True

    return not has_failures


def _validate_export_name(name):
    """Validate an export filename stem. Keep aliases inside temp_dir."""
    if not name or not name.strip():
        raise ValueError("--export-name must not be empty")
    if '\x00' in name or '/' in name or '\\' in name:
        raise ValueError("--export-name must be a filename stem, not a path")
    return name.strip()


def export_named_aliases(temp_dir, export_name):
    """Copy canonical outputs to optional user-facing filenames.

    Canonical artifacts remain untouched. The alias names use export_name as a
    filename stem, with book_doc.html receiving a _doc suffix to avoid colliding
    with the web HTML alias.
    """
    stem = _validate_export_name(export_name)
    mappings = {
        "book.html": f"{stem}.html",
        "book_doc.html": f"{stem}_doc.html",
        "book.docx": f"{stem}.docx",
        "book.epub": f"{stem}.epub",
        "book.pdf": f"{stem}.pdf",
    }
    copied = []
    for src_name, dst_name in mappings.items():
        src = os.path.join(temp_dir, src_name)
        if not os.path.exists(src):
            continue
        dst = os.path.join(temp_dir, dst_name)
        if os.path.abspath(src) == os.path.abspath(dst):
            continue
        shutil.copy2(src, dst)
        copied.append(dst_name)
    return copied
