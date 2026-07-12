#!/usr/bin/env python
"""_mab_html.py — Convert merged output.md to templated HTML.

Carries the three-stage converter chain (pandoc -> python-markdown -> basic
regex), template application, separator post-processing and the top-level
convert_md_to_html orchestrator. Extracted verbatim from merge_and_build.py
(no behavior change).
"""

import os
import re
import subprocess
import html as _html_lib

from _mab_common import SCRIPT_DIR
from _mab_images import _check_generated_html_sanity

# Try to import markdown
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


# =============================================================================
# Step 5: Convert markdown to HTML
# =============================================================================

def check_pandoc_available():
    """Check if pandoc is available"""
    try:
        subprocess.run(['pandoc', '--version'], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def convert_with_pandoc(md_file, html_file, title, lang_attr):
    """Convert markdown to HTML using pandoc"""
    cmd = [
        'pandoc', md_file, '-o', html_file,
        '--standalone',
        '--metadata', f'title={title}',
        '--metadata', f'lang={lang_attr}',
        '--from', 'markdown+smart+east_asian_line_breaks',
        '--to', 'html5'
    ]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        print("Converted with pandoc")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Pandoc conversion failed: {e.stderr}")
        return False


def convert_with_python_markdown(md_file, html_file, title):
    """Convert markdown to HTML using python-markdown (fallback 1)"""
    if not MARKDOWN_AVAILABLE:
        return False

    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        extensions = ['toc', 'tables', 'fenced_code', 'codehilite', 'nl2br']
        md = markdown.Markdown(extensions=extensions)
        html_content = md.convert(md_content)

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        print("Converted with python-markdown (fallback)")
        return True
    except Exception as e:
        print(f"python-markdown conversion failed: {e}")
        return False


def convert_with_basic_regex(md_file, html_file, title):
    """Convert markdown to HTML using basic regex (fallback 2)"""
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html_content = md_content

        # Headers
        html_content = re.sub(r'^#### (.*?)$', r'<h4>\1</h4>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html_content, flags=re.MULTILINE)
        html_content = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html_content, flags=re.MULTILINE)

        # Bold and italic
        html_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html_content)
        html_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html_content)
        html_content = re.sub(r'_(.*?)_', r'<em>\1</em>', html_content)

        # Images — escape alt and src so quotes in alt text don't break the tag
        def _md_img_to_html(m):
            alt = _html_lib.escape(m.group(1), quote=True)
            src = _html_lib.escape(m.group(2), quote=True)
            return f'<img src="{src}" alt="{alt}">'
        html_content = re.sub(r'!\[([^\]]*)\]\(([^)]*)\)', _md_img_to_html, html_content)

        # Links
        html_content = re.sub(r'\[([^\]]*)\]\(([^)]*)\)', r'<a href="\2">\1</a>', html_content)

        # Lists and paragraphs
        lines = html_content.split('\n')
        result_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('- '):
                if not in_list:
                    result_lines.append('<ul>')
                    in_list = 'ul'
                item = stripped[2:]
                result_lines.append(f'<li>{item}</li>')
            elif re.match(r'^\d+\. ', stripped):
                if not in_list:
                    result_lines.append('<ol>')
                    in_list = 'ol'
                item = re.sub(r'^\d+\. ', '', stripped)
                result_lines.append(f'<li>{item}</li>')
            else:
                if in_list:
                    result_lines.append(f'</{in_list}>')
                    in_list = False
                if stripped and not stripped.startswith('<'):
                    result_lines.append(f'<p>{line}</p>')
                else:
                    result_lines.append(line)

        if in_list:
            result_lines.append(f'</{in_list}>')

        html_content = '\n'.join(result_lines)

        # Page separators
        html_content = re.sub(r'<p>---</p>', '<div class="page-separator"></div>', html_content)

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
</head>
<body>
{html_content}
</body>
</html>"""

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(full_html)

        print("Converted with basic regex (fallback 2)")
        return True
    except Exception as e:
        print(f"Basic regex conversion failed: {e}")
        return False


def apply_template_to_html(html_content, template_file, output_file, title, lang_cfg, author=None):
    """Apply a template to HTML content with language-aware substitutions"""
    if not template_file or not os.path.exists(template_file):
        print(f"Warning: Template {template_file} not found")
        return False

    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            template_content = f.read()

        if '$body$' in template_content:
            full_html = template_content.replace('$body$', html_content)
        elif '{{content}}' in template_content:
            full_html = template_content.replace('{{content}}', html_content)
        else:
            if '</body>' in template_content:
                full_html = template_content.replace('</body>', f'{html_content}\n</body>')
            else:
                full_html = template_content + html_content

        # Replace all template placeholders
        full_html = full_html.replace('$title$', title)
        full_html = full_html.replace('$lang$', lang_cfg['lang_attr'])
        full_html = full_html.replace('$body_font$', lang_cfg['font_family'])
        full_html = full_html.replace('$toc_label$', lang_cfg['toc_label'])

        # Inject author meta tag into <head> so calibre_html_publish.py can extract it
        if author:
            author_meta = f'<meta name="author" content="{author}">'
            if '<head>' in full_html or '<head ' in full_html:
                full_html = re.sub(
                    r'(<head[^>]*>)',
                    r'\1\n    ' + author_meta,
                    full_html,
                    count=1,
                    flags=re.IGNORECASE
                )

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(full_html)
        return True
    except Exception as e:
        print(f"Error applying template: {e}")
        return False


def process_html_separators(html_file):
    """Process page separators in HTML"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()

        content = re.sub(r'<hr\s*/?>', '<div class="page-separator"></div>', content)
        content = re.sub(r'<p>\s*---\s*</p>', '<div class="page-separator"></div>', content)

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error processing separators: {e}")


def convert_md_to_html(temp_dir, title, lang_cfg, author=None):
    """Convert output.md to HTML with templates"""
    print("=== Converting markdown to HTML ===")

    md_file = os.path.join(temp_dir, 'output.md')
    if not os.path.exists(md_file):
        print("Error: output.md not found.")
        return False

    book_doc_file = os.path.join(temp_dir, 'book_doc.html')

    # Skip HTML generation if book_doc.html exists and is newer than output.md
    if os.path.exists(book_doc_file):
        if os.path.getmtime(book_doc_file) > os.path.getmtime(md_file):
            if _check_generated_html_sanity(book_doc_file):
                print("Skipping HTML generation - book_doc.html is up to date")
                return True
            print("Stale book_doc.html failed image sanity — regenerating")
            os.remove(book_doc_file)
        else:
            print("Re-generating HTML - output.md is newer")

    temp_html_file = os.path.join(temp_dir, 'output.html')

    # Try pandoc -> python-markdown -> basic regex
    success = False
    if check_pandoc_available():
        success = convert_with_pandoc(md_file, temp_html_file, title, lang_cfg['lang_attr'])

    if not success:
        success = convert_with_python_markdown(md_file, temp_html_file, title)

    if not success:
        success = convert_with_basic_regex(md_file, temp_html_file, title)

    if not success:
        print("Error: All markdown-to-HTML converters failed")
        return False

    process_html_separators(temp_html_file)

    # Extract body content
    try:
        with open(temp_html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
    body_content = body_match.group(1).strip() if body_match else html_content

    # Generate book_doc.html with ebook template
    template_ebook = os.path.join(SCRIPT_DIR, 'template_ebook.html')
    book_doc_file = os.path.join(temp_dir, 'book_doc.html')
    apply_template_to_html(body_content, template_ebook, book_doc_file, title, lang_cfg, author)

    # Generate book.html with web template
    template_web = os.path.join(SCRIPT_DIR, 'template.html')
    book_file = os.path.join(temp_dir, 'book.html')
    apply_template_to_html(body_content, template_web, book_file, title, lang_cfg, author)

    if not _check_generated_html_sanity(book_doc_file):
        return False
    if not _check_generated_html_sanity(book_file):
        return False

    print("Generated: output.html, book_doc.html, book.html")
    return True
