#!/usr/bin/env python
"""_mab_common.py — Shared foundation for the merge_and_build subsystem.

Holds the language configuration table, config.txt loader and the natural-sort
key used across the merge & build pipeline. Extracted verbatim from
merge_and_build.py as part of the decomposition (no behavior change).
"""

import os
import sys
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# Language configuration — single source of truth for lang-dependent values
# =============================================================================

LANG_CONFIG = {
    'zh': {
        'lang_attr': 'zh-CN',
        'font_family': "'FangSong', '仿宋', 'STFangSong', '华文仿宋', serif",
        'font_family_ebook': '"FangSong", "FangSong_GB2312", "仿宋", "仿宋_GB2312", "STFangSong", "SimSun", serif',
        'toc_label': '目录',
        'pdf_font': 'FangSong',
    },
    'en': {
        'lang_attr': 'en',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'toc_label': 'Contents',
        'pdf_font': 'Georgia',
    },
    'ja': {
        'lang_attr': 'ja',
        'font_family': "'Hiragino Mincho ProN', 'Yu Mincho', 'MS Mincho', serif",
        'font_family_ebook': '"Hiragino Mincho ProN", "Yu Mincho", "MS Mincho", serif',
        'toc_label': '目次',
        'pdf_font': 'Hiragino Mincho ProN',
    },
    'ko': {
        'lang_attr': 'ko',
        'font_family': "'Nanum Myeongjo', 'Batang', serif",
        'font_family_ebook': '"Nanum Myeongjo", "Batang", serif',
        'toc_label': '목차',
        'pdf_font': 'Nanum Myeongjo',
    },
    'fr': {
        'lang_attr': 'fr',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'toc_label': 'Table des matières',
        'pdf_font': 'Georgia',
    },
    'de': {
        'lang_attr': 'de',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'toc_label': 'Inhaltsverzeichnis',
        'pdf_font': 'Georgia',
    },
    'es': {
        'lang_attr': 'es',
        'font_family': "Georgia, 'Times New Roman', Times, serif",
        'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
        'toc_label': 'Índice',
        'pdf_font': 'Georgia',
    },
}

# Default fallback for unknown languages
_DEFAULT_LANG_CONFIG = {
    'lang_attr': 'en',
    'font_family': "Georgia, 'Times New Roman', Times, serif",
    'font_family_ebook': 'Georgia, "Times New Roman", Times, serif',
    'toc_label': 'Contents',
    'pdf_font': 'Georgia',
}


def get_lang_config(lang_code):
    """Get language config, falling back to defaults for unknown languages."""
    return LANG_CONFIG.get(lang_code, _DEFAULT_LANG_CONFIG)


def load_config(temp_dir):
    """Load configuration from config.txt"""
    config_file = os.path.join(temp_dir, 'config.txt')
    if not os.path.exists(config_file):
        print("Error: config.txt not found in temp directory.")
        sys.exit(1)

    config = {}
    with open(config_file, 'r', encoding='utf-8') as f:
        for line in f:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config


def natural_sort_key(text):
    """Natural sorting key for filenames with numbers"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', text)]
