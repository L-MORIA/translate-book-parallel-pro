#!/usr/bin/env python
"""_mab_toc.py — Generate and insert a table of contents into book.html.

Two implementations (BeautifulSoup primary, regex fallback) selected by
availability of bs4 at import time. Extracted from merge_and_build.py; TOC
anchor text is HTML-escaped (heading text comes from the untrusted source
book) and the regex fallback inserts ids via a re.sub callback.
"""

import os
import re
import html as _html_lib

# Try to import BeautifulSoup for TOC generation
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# =============================================================================
# Step 6: Add TOC
# =============================================================================

def generate_heading_id(text, existing_ids):
    """Generate unique ID for heading"""
    base_id = re.sub(r'[^\w\s-]', '', text.lower())
    base_id = re.sub(r'[-\s]+', '-', base_id)
    base_id = base_id.strip('-')

    if not base_id:
        base_id = 'heading'

    heading_id = base_id
    counter = 1
    while heading_id in existing_ids:
        heading_id = f"{base_id}-{counter}"
        counter += 1

    return heading_id


def generate_simple_toc_html(toc_data):
    """Generate simple HTML for table of contents"""
    if not toc_data:
        return ""

    toc_html = '<ul>\n'
    current_level = 1

    for item in toc_data:
        level = item['level']
        text = item['text']
        heading_id = item['id']

        if level > current_level:
            while current_level < level:
                toc_html += '<li><ul>\n'
                current_level += 1
        elif level < current_level:
            while current_level > level:
                toc_html += '</ul></li>\n'
                current_level -= 1

        # Heading text comes from the (untrusted) source book — escape it so
        # it renders as text, never as markup inside the TOC.
        text_escaped = _html_lib.escape(text, quote=True)
        toc_html += f'<li><a href="#{heading_id}">{text_escaped}</a></li>\n'

    while current_level > 1:
        toc_html += '</ul></li>\n'
        current_level -= 1

    toc_html += '</ul>\n'
    return toc_html


def insert_toc_with_bs4(html_file):
    """Insert TOC using BeautifulSoup"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    soup = BeautifulSoup(html_content, 'html.parser')

    toc_data = []
    existing_ids = []

    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        level = int(heading.name[1])
        text = heading.get_text().strip()
        if not text:
            continue

        heading_id = generate_heading_id(text, existing_ids)
        existing_ids.append(heading_id)
        heading['id'] = heading_id
        toc_data.append({'level': level, 'text': text, 'id': heading_id})

    if not toc_data:
        print("No headings found for TOC")
        return False

    toc_html = generate_simple_toc_html(toc_data)

    toc_content_div = soup.find('div', class_='toc-content')
    if toc_content_div:
        toc_content_div.clear()
        toc_soup = BeautifulSoup(toc_html, 'html.parser')
        toc_content_div.append(toc_soup)
        print(f"TOC inserted ({len(toc_data)} headings)")
    else:
        print("Warning: .toc-content div not found, TOC not inserted")
        return False

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        return True
    except Exception as e:
        print(f"Error saving HTML file: {e}")
        return False


def insert_toc_with_regex(html_file):
    """Insert TOC using regex (fallback)"""
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return False

    heading_pattern = re.compile(r'<(h[1-6])([^>]*)>(.*?)</\1>',
                                 re.IGNORECASE | re.DOTALL)
    if not heading_pattern.search(html_content):
        print("No headings found for TOC")
        return False

    # Insert ids and collect TOC entries in a single pass. A re.sub callback
    # (not a replacement string) is required: heading text is untrusted and
    # may contain backslash sequences (\g, \1) that would otherwise crash
    # re.sub or splice match groups into the document.
    toc_entries = []
    seen = [0]

    def _number_heading(match):
        tag, attrs, text = match.group(1), match.group(2), match.group(3)
        seen[0] += 1
        level = int(tag[1])
        clean_text = re.sub(r'<[^>]+>', '', text).strip()

        # pandoc often pre-assigns heading ids — reuse them instead of adding
        # a duplicate id attribute
        existing_id = re.search(r'\bid\s*=\s*("|\')(.*?)\1', attrs, re.IGNORECASE)
        if existing_id and existing_id.group(2):
            heading_id = existing_id.group(2)
            replacement = match.group(0)
        else:
            heading_id = f"heading-{seen[0]}"
            replacement = f'<{tag}{attrs} id="{heading_id}">{text}</{tag}>'

        indent = '  ' * (level - 1)
        toc_entries.append(
            f'{indent}<li><a href="#{heading_id}">'
            f'{_html_lib.escape(clean_text, quote=True)}</a></li>\n'
        )
        return replacement

    html_content = heading_pattern.sub(_number_heading, html_content)

    toc_html = '<ul>\n' + ''.join(toc_entries) + '</ul>\n'

    toc_content_pattern = r'(<div[^>]*class="toc-content[^"]*"[^>]*>).*?(</div>)'
    if re.search(toc_content_pattern, html_content, re.DOTALL):
        html_content = re.sub(
            toc_content_pattern,
            lambda m: m.group(1) + toc_html + m.group(2),
            html_content,
            flags=re.DOTALL
        )
        print(f"TOC inserted ({seen[0]} headings)")
    else:
        print("Warning: .toc-content div not found")
        return False

    try:
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        return True
    except Exception as e:
        print(f"Error saving HTML file: {e}")
        return False


def add_toc(temp_dir):
    """Add TOC to book.html"""
    print("=== Adding Table of Contents ===")

    html_file = os.path.join(temp_dir, 'book.html')
    if not os.path.exists(html_file):
        print("Warning: book.html not found, skipping TOC")
        return False

    if BS4_AVAILABLE:
        return insert_toc_with_bs4(html_file)
    else:
        return insert_toc_with_regex(html_file)
