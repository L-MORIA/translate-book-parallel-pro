#!/usr/bin/env python
"""_mab_toc.py — Generate and insert a table of contents into book.html.

Two implementations (BeautifulSoup primary, regex fallback) selected by
availability of bs4 at import time. Extracted verbatim from merge_and_build.py
(no behavior change).
"""

import os
import re

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

        toc_html += f'<li><a href="#{heading_id}">{text}</a></li>\n'

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

    heading_pattern = r'<(h[1-6])(?:[^>]*)>(.*?)</\1>'
    headings = re.findall(heading_pattern, html_content, re.IGNORECASE | re.DOTALL)

    if not headings:
        print("No headings found for TOC")
        return False

    toc_html = '<ul>\n'
    for i, (tag, text) in enumerate(headings):
        level = int(tag[1])
        clean_text = re.sub(r'<[^>]+>', '', text).strip()
        heading_id = f"heading-{i+1}"

        old_heading = f'<{tag}>{text}</{tag}>'
        new_heading = f'<{tag} id="{heading_id}">{text}</{tag}>'
        html_content = html_content.replace(old_heading, new_heading, 1)

        if level > 1:
            for _ in range(level - 1):
                toc_html += '  '
        toc_html += f'<li><a href="#{heading_id}">{clean_text}</a></li>\n'

    toc_html += '</ul>\n'

    toc_content_pattern = r'(<div[^>]*class="toc-content[^"]*"[^>]*>).*?(</div>)'
    if re.search(toc_content_pattern, html_content, re.DOTALL):
        html_content = re.sub(
            toc_content_pattern,
            r'\1' + toc_html + r'\2',
            html_content,
            flags=re.DOTALL
        )
        print(f"TOC inserted ({len(headings)} headings)")
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
