#!/usr/bin/env python
"""
translate-book-parallel — dependency setup script.

Verifies and installs all prerequisites for the skill.
Run: python scripts/setup.py
"""

import subprocess, sys, os, platform

PASS = "  ✅"
FAIL = "  ❌"
SKIP = "  ➖"

def sh(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip().split('\n')[0]
    except Exception as e:
        return False, str(e)

def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 8
    print(f"{PASS if ok else FAIL} Python {v.major}.{v.minor}.{v.micro} (need >=3.8)")
    return ok

def check_calibre():
    ok, ver = sh("ebook-convert --version")
    if ok:
        print(f"{PASS} Calibre: {ver}")
    else:
        print(f"{FAIL} Calibre (ebook-convert) not found — install from https://calibre-ebook.com/")
    return ok

def check_pandoc():
    ok, ver = sh("pandoc --version | head -1")
    if ok:
        print(f"{PASS} Pandoc: {ver}")
    else:
        print(f"{FAIL} Pandoc not found — run: winget install JohnMacFarlane.Pandoc")
    return ok

def check_pip_module(name):
    ok, _ = sh(f"python -c \"import {name}; print({name}.__version__)\"")
    if ok:
        ver = eval(f"__import__('{name}').__version__")
        print(f"{PASS} {name} {ver}")
    else:
        print(f"{FAIL} {name} not installed — run: pip install {name}")
    return ok

def install_pip(name):
    print(f"  → Installing {name}...", end=" ")
    ok, out = sh(f"pip install {name}")
    print("OK" if ok else f"FAIL: {out}")
    return ok

def main():
    print("\n" + "=" * 55)
    print(" translate-book-parallel — Setup & Verification")
    print("=" * 55 + "\n")

    print("[1/5] Python")
    py_ok = check_python()

    print("\n[2/5] System tools")
    cal_ok = check_calibre()
    pan_ok = check_pandoc()

    print("\n[3/5] Python packages")
    pypa_ok = check_pip_module("pypandoc")
    bs4_ok = check_pip_module("bs4")

    print("\n[4/5] Auto-install missing pip packages")
    if not pypa_ok:
        pypa_ok = install_pip("pypandoc")
    if not bs4_ok:
        bs4_ok = install_pip("beautifulsoup4")

    print("\n[5/5] Final verification")
    all_ok = all([py_ok, cal_ok, pan_ok, pypa_ok, bs4_ok])
    if all_ok:
        print(f"{PASS} All dependencies satisfied — skill ready to use")
    else:
        print(f"{FAIL} Some dependencies missing — see above")
        sys.exit(1)

    print("\n" + "=" * 55)
    print(" Quick start:")
    print("   1. Install skill in Hermes:")
    print("      cp -r translate-book-parallel ${HERMES_HOME:-$HOME/.hermes}/skills/")
    print("   2. /reload-skills in chat")
    print("   3. Say: переведи D:\\book.epub на русский")
    print("=" * 55 + "\n")

if __name__ == "__main__":
    main()
